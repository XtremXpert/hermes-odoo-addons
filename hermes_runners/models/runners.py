# Part of the hermes_runners Odoo module. See LICENSE for details.
"""État des runners GitHub Actions auto-hébergés (ARC).

Deux sources, et la distinction compte :

* le **cluster** sait quels runners existent — ARC crée un `EphemeralRunner`
  par job attribué, avec sa phase et son identifiant GitHub. C'est direct,
  sans jeton, sans quota ;
* **GitHub** sait ce qui *attend* — un job en file n'a pas encore de pod, donc
  n'apparaît nulle part dans Kubernetes. Cette moitié demande un jeton et vit
  dans `github_queue_snapshot`, qui échoue proprement quand le jeton manque.

Un tableau de bord qui ne montrerait que le cluster afficherait « tout va bien »
pendant qu'une file grossit. C'est pour cette raison que les deux vues existent
et que la file est affichée séparément, avec son propre indicateur d'échec.
"""

import logging
from collections import Counter

from kubernetes import client

from odoo import api
from odoo import fields
from odoo import models

_logger = logging.getLogger(__name__)


def summarize_pools(pools, runners):
    """Agrégation pure, hors appel réseau : testable seule.

    `pools` : [{name, min, max, repo}]
    `runners` : [{pool, phase, ...}]

    Le taux d'occupation est le rapport au maximum, pas au nombre de pods : un
    pool à 2/2 est saturé, un pool à 0/1 est libre — et un pool à 0/0 n'existe
    que s'il est en pause (maxRunners = 0).
    """
    par_pool = Counter(r["pool"] for r in runners)
    resume = []
    for pool in pools:
        actifs = par_pool.get(pool["name"], 0)
        maximum = pool.get("max") or 0
        resume.append(
            {
                "name": pool["name"],
                "repo": pool.get("repo") or "",
                "min": pool.get("min") or 0,
                "max": maximum,
                "running": actifs,
                "free": max(maximum - actifs, 0),
                "saturated": bool(maximum) and actifs >= maximum,
                "paused": maximum == 0,
            }
        )
    return sorted(resume, key=lambda p: p["name"])


class ArcRunners(models.AbstractModel):
    _name = "arc.runners"
    _description = "Runners GitHub Actions — instantanés"

    # ── lecture du cluster ────────────────────────────────────────────────────
    @api.model
    def _clusters(self):
        return self.env["k8s.cluster"].sudo().search([("active", "=", True)])

    @api.model
    def _lire_cluster(self, cluster):
        """Runners et pools d'un cluster, ou une erreur lisible.

        Une erreur sur un cluster ne doit pas masquer les autres : elle est
        rapportée dans l'entrée, jamais levée.
        """
        entree = {
            "cluster": cluster.name,
            "reachable": False,
            "error": False,
            "pools": [],
            "runners": [],
        }
        try:
            api_client = cluster._get_k8s_client()
            custom = client.CustomObjectsApi(api_client)

            pools = custom.list_cluster_custom_object(
                group="actions.github.com",
                version="v1alpha1",
                plural="autoscalingrunnersets",
            )
            for item in pools.get("items", []):
                spec = item.get("spec") or {}
                entree["pools"].append(
                    {
                        "name": item["metadata"]["name"],
                        "namespace": item["metadata"].get("namespace") or "",
                        "min": spec.get("minRunners") or 0,
                        "max": spec.get("maxRunners") or 0,
                        "repo": (spec.get("githubConfigUrl") or "").rsplit("/", 1)[-1],
                    }
                )

            pods = custom.list_cluster_custom_object(
                group="actions.github.com",
                version="v1alpha1",
                plural="ephemeralrunners",
            )
            now = fields.Datetime.now()
            for item in pods.get("items", []):
                meta = item.get("metadata") or {}
                statut = item.get("status") or {}
                labels = meta.get("labels") or {}
                cree = meta.get("creationTimestamp")
                age = ""
                if cree:
                    age = self._age_minutes(cree, now)
                entree["runners"].append(
                    {
                        "name": meta.get("name") or "",
                        "pool": labels.get("actions.github.com/scale-set-name") or "",
                        "phase": statut.get("phase") or "?",
                        "runner_id": statut.get("runnerId") or 0,
                        "age_minutes": age,
                        "namespace": meta.get("namespace") or "",
                    }
                )
            entree["pools"] = summarize_pools(entree["pools"], entree["runners"])
            entree["reachable"] = True
        # Un cluster muet ne doit pas masquer les autres, et le client
        # Kubernetes lève des types variés : capturer large est le but.
        except Exception as error:
            entree["error"] = str(error)[:200]
            _logger.warning("Runners illisibles sur %s", cluster.name, exc_info=True)
        return entree

    @staticmethod
    def _age_minutes(creation_timestamp, now):
        """Ancienneté lisible d'un runner, en minutes.

        L'âge est celui du POD, pas celui du job.

        Un pool avec `minRunners > 0` garde un pod pré-provisionné en attente :
        `arc-maison` affiche ainsi treize jours d'âge sans qu'aucun job ne soit
        bloqué. L'âge ne devient une information sur un job qu'une fois la phase
        connue — et le module ne lit pas encore le job lui-même. Il vaut donc
        mieux l'afficher comme une ancienneté de pod que comme une alerte.
        """
        try:
            cree = fields.Datetime.to_datetime(creation_timestamp).replace(tzinfo=None)
        except (ValueError, TypeError):
            return ""
        minutes = int((now - cree).total_seconds() // 60)
        return max(minutes, 0)

    @api.model
    def runners_snapshot(self):
        """Liste des runners de tous les clusters actifs, à plat."""
        payload = [self._lire_cluster(cluster) for cluster in self._clusters()]
        tous = []
        for entree in payload:
            for runner in entree["runners"]:
                tous.append({**runner, "cluster": entree["cluster"]})
        return {
            "generated_at": fields.Datetime.to_string(fields.Datetime.now()),
            "clusters": payload,
            "runners": sorted(tous, key=lambda r: (r["cluster"], r["pool"], r["name"])),
            "totals": {
                "clusters": len(payload),
                "reachable": len([e for e in payload if e["reachable"]]),
                "runners": len(tous),
                "running": len([r for r in tous if r["phase"] == "Running"]),
                "pending": len([r for r in tous if r["phase"] == "Pending"]),
                "pools": sum(len(e["pools"]) for e in payload),
                "saturated": sum(1 for e in payload for p in e["pools"] if p["saturated"]),
            },
        }

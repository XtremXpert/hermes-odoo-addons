#!/usr/bin/env bash
#
# Vendorise le bundle UMD officiel de @wazo/sdk dans le module.
#
# Pourquoi vendoriser plutôt qu'importer la source : le paquet publie un
# bundle UMD (`dist/wazo-sdk.js`) avec TOUTES ses dépendances inlinées
# (sip.js 0.21.2 — la même version que notre SIP.js vendorisé —,
# webrtc-adapter, moment, jsrsasign…). Utiliser ce fichier évite de
# reconstruire le paquet avec les polyfills webpack 5 dont la source a
# besoin. C'est le seul artefact dont on dépende.
#
# Pourquoi l'envelopper : le repli du UMD fait `root[i] = a[i]`, c'est-à-dire
# qu'il ÉTALE ses 66 exports sur l'objet global (Session, Contact, Line,
# Profile…). Dans une page Odoo, ces noms génériques pollueraient l'espace
# de noms partagé. L'IIFE ci-dessous force la branche CommonJS du UMD (en
# lui fournissant des `module`/`exports` locaux) et n'expose qu'UN nom :
# `globalThis.WazoSDK`.
#
# Usage : wazo_phone/tools/vendor_wazo_sdk.sh
set -euo pipefail

SDK_VERSION="${1:-0.49.5}"
MODULE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${MODULE_DIR}/static/lib/wazo-sdk.js"
WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

echo "→ téléchargement de @wazo/sdk@${SDK_VERSION} depuis le registre npm"
cd "${WORK}"
npm pack "@wazo/sdk@${SDK_VERSION}" >/dev/null 2>&1
tar -xzf wazo-sdk-*.tgz package/dist/wazo-sdk.js

echo "→ enveloppement (exports capturés sous window.WazoSDK)"
python3 - "${WORK}/package/dist/wazo-sdk.js" "${DEST}" "${SDK_VERSION}" <<'PY'
import sys

source, dest, version = sys.argv[1], sys.argv[2], sys.argv[3]
body = open(source, encoding="utf-8").read()

header = f"""/**
 * @wazo/sdk {version} — bundle UMD officiel, VENDORISÉ. NE PAS ÉDITER.
 *
 * Source : https://registry.npmjs.org/@wazo/sdk/-/wazo-sdk-{version}.tgz
 *          (fichier ``dist/wazo-sdk.js``, dépendances inlinées dont
 *          sip.js 0.21.2 et webrtc-adapter).
 * Régénérer : ``wazo_phone/tools/vendor_wazo_sdk.sh``
 *
 * Le bundle est enveloppé dans une IIFE qui force sa branche CommonJS et
 * n'expose que ``window.WazoSDK`` : sans cela, son repli écraserait la
 * racine avec 66 exports aux noms génériques (Session, Contact, Line…).
 */
(function () {{
    var module = {{ exports: {{}} }};
    var exports = module.exports;
"""
footer = """
    globalThis.WazoSDK = module.exports;
})();
"""

with open(dest, "w", encoding="utf-8") as handle:
    handle.write(header)
    handle.write(body)
    handle.write(footer)
print(f"   écrit {dest} ({len(header) + len(body) + len(footer)} octets)")
PY

echo "→ vérification (chargement réel et lecture des exports)"
node - "${DEST}" <<'JS'
const fs = require("fs");
const path = process.argv[2];
const sandbox = { window: {}, navigator: { userAgent: "node" } };
sandbox.globalThis = sandbox;
const fn = new Function("globalThis", fs.readFileSync(path, "utf8"));
fn(sandbox);
const sdk = sandbox.WazoSDK;
if (!sdk || typeof sdk.WebRTCClient !== "function") {
    console.error("   ÉCHEC : WazoSDK.WebRTCClient absent");
    process.exit(1);
}
if (typeof sdk.SIP !== "undefined") {
    console.error("   ÉCHEC : collision de global 'SIP' avec notre SIP.js");
    process.exit(1);
}
console.log(`   OK : ${Object.keys(sdk).length} exports, WebRTCClient présent, aucun global 'SIP'`);
JS

echo "→ terminé"

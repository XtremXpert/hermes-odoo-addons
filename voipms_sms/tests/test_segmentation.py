# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests de la segmentation et de la normalisation des numéros.

Contrats validés en production (voipms_reply_watch.py) :
- numéros NANP normalisés sur 11 chiffres (préfixe 1) ;
- segmentation conservatrice à 150 caractères par appel sendSMS ;
- messages vides ou > 1600 caractères rejetés localement.
"""

from odoo.addons.voipms_sms.services.sms_segmentation import MAX_GLOBAL
from odoo.addons.voipms_sms.services.sms_segmentation import MAX_SEGMENT
from odoo.addons.voipms_sms.services.sms_segmentation import SEGMENT_PREFIX_LEN
from odoo.addons.voipms_sms.services.sms_segmentation import normalize_nanp
from odoo.addons.voipms_sms.services.sms_segmentation import split_sms
from odoo.tests import tagged
from odoo.tests.common import BaseCase


@tagged("voipms_sms", "post_install", "-at_install")
class TestNormalizeNanp(BaseCase):
    def test_ten_digits_get_country_prefix(self):
        """Vérifie qu'un numéro à dix chiffres reçoit le préfixe pays."""
        self.assertEqual(normalize_nanp("4184803381"), "14184803381")

    def test_eleven_digit_number_kept(self):
        """Vérifie qu'un numéro à onze chiffres est conservé."""
        self.assertEqual(normalize_nanp("14184803381"), "14184803381")

    def test_pretty_format_is_normalized(self):
        """Vérifie qu'un numéro mis en forme est normalisé."""
        self.assertEqual(normalize_nanp("+1 (418) 480-3381"), "14184803381")

    def test_non_nanp_rejected(self):
        """Vérifie qu'un numéro non NANP est refusé."""
        with self.assertRaises(ValueError):
            normalize_nanp("51412345")  # 8 chiffres

    def test_empty_rejected(self):
        """Vérifie qu'un numéro vide est refusé."""
        with self.assertRaises(ValueError):
            normalize_nanp("")

    def test_international_rejected(self):
        """Vérifie qu'un numéro international non NANP est refusé."""
        with self.assertRaises(ValueError):
            normalize_nanp("+33 6 12 34 56 78")  # non-NANP


@tagged("voipms_sms", "post_install", "-at_install")
class TestSplitSms(BaseCase):
    def test_short_message_single_part(self):
        """Vérifie qu'un message court tient en un segment."""
        self.assertEqual(split_sms("Bonjour"), ["Bonjour"])

    def test_message_fits_in_one_segment(self):
        """Vérifie qu'un message de 140 caractères tient en un segment."""
        text = "a" * 140
        self.assertEqual(split_sms(text), [text])

    def test_long_message_is_segmented(self):
        """Vérifie qu'un message long est découpé en segments."""
        text = " ".join(["mot%d" % i for i in range(120)])  # bien > 150
        parts = split_sms(text)
        self.assertGreater(len(parts), 1)
        for i, part in enumerate(parts, start=1):
            self.assertTrue(part.startswith("%d/%d " % (i, len(parts))))
            self.assertLessEqual(len(part), 150)
            # Le contenu reconstitué contient le texte original (mots)
        joined = "".join(
            p.replace("%d/%d " % (i, len(parts)), "", 1) for i, p in enumerate(parts, start=1)
        )
        self.assertIn("mot0", joined)
        self.assertIn("mot119", joined)

    def test_empty_message_rejected(self):
        """Vérifie qu'un message vide est refusé."""
        with self.assertRaises(ValueError):
            split_sms("   ")

    def test_oversized_message_rejected(self):
        """Vérifie qu'un message de plus de 1600 caractères est refusé."""
        with self.assertRaises(ValueError):
            split_sms("a" * 1601)

    def test_global_cap_is_1600(self):
        """Vérifie que les plafonds sont 150 par segment et 1600 au total."""
        self.assertEqual(MAX_GLOBAL, 1600)
        self.assertEqual(MAX_SEGMENT, 150)
        self.assertGreater(SEGMENT_PREFIX_LEN, 0)

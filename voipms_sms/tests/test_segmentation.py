# Part of the voipms_sms Odoo module. See LICENSE for details.
"""Tests de la segmentation et de la normalisation des numéros.

Contrats validés en production (voipms_reply_watch.py) :
- numéros NANP normalisés sur 11 chiffres (préfixe 1) ;
- segmentation conservatrice à 150 caractères par appel sendSMS ;
- messages vides ou > 1600 caractères rejetés localement.
"""

from odoo.tests import tagged
from odoo.tests.common import BaseCase

from odoo.addons.voipms_sms.services.sms_segmentation import (
    MAX_GLOBAL,
    MAX_SEGMENT,
    SEGMENT_PREFIX_LEN,
    normalize_nanp,
    split_sms,
)


@tagged('voipms_sms', 'post_install', '-at_install')
class TestNormalizeNanp(BaseCase):

    def test_ten_digits_get_country_prefix(self):
        self.assertEqual(normalize_nanp('4184803381'), '14184803381')

    def test_eleven_digit_number_kept(self):
        self.assertEqual(normalize_nanp('14184803381'), '14184803381')

    def test_pretty_format_is_normalized(self):
        self.assertEqual(normalize_nanp('+1 (418) 480-3381'), '14184803381')

    def test_non_nanp_rejected(self):
        with self.assertRaises(ValueError):
            normalize_nanp('51412345')  # 8 chiffres

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            normalize_nanp('')

    def test_international_rejected(self):
        with self.assertRaises(ValueError):
            normalize_nanp('+33 6 12 34 56 78')  # non-NANP


@tagged('voipms_sms', 'post_install', '-at_install')
class TestSplitSms(BaseCase):

    def test_short_message_single_part(self):
        self.assertEqual(split_sms('Bonjour'), ['Bonjour'])

    def test_message_fits_in_one_segment(self):
        text = 'a' * 140
        self.assertEqual(split_sms(text), [text])

    def test_long_message_is_segmented(self):
        text = ' '.join(['mot%d' % i for i in range(120)])  # bien > 150
        parts = split_sms(text)
        self.assertGreater(len(parts), 1)
        for i, part in enumerate(parts, start=1):
            self.assertTrue(part.startswith('%d/%d ' % (i, len(parts))))
            self.assertLessEqual(len(part), 150)
            # Le contenu reconstitué contient le texte original (mots)
        joined = ''.join(p.replace('%d/%d ' % (i, len(parts)), '', 1)
                         for i, p in enumerate(parts, start=1))
        self.assertIn('mot0', joined)
        self.assertIn('mot119', joined)

    def test_empty_message_rejected(self):
        with self.assertRaises(ValueError):
            split_sms('   ')

    def test_oversized_message_rejected(self):
        with self.assertRaises(ValueError):
            split_sms('a' * 1601)

    def test_global_cap_is_1600(self):
        self.assertEqual(MAX_GLOBAL, 1600)
        self.assertEqual(MAX_SEGMENT, 150)
        self.assertGreater(SEGMENT_PREFIX_LEN, 0)

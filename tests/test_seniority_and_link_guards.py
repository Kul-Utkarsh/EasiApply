import unittest
from unittest.mock import MagicMock
from src.scraper.parser import JobParser

class TestSeniorityAndLinkGuards(unittest.TestCase):
    def test_junior_seniority_filter(self):
        # Junior target rejects Lead based on title alone (no explicit YOE)
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Lead Product Designer",
            post_text="We are hiring a Lead Designer to head our product design team.",
            target_seniority="Associate / Junior Professional",
            max_yoe=2
        )
        self.assertFalse(fit)
        self.assertIn("seniority", reason.lower())

        # Senior role rejected based on title alone (no explicit YOE)
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Senior UX Designer",
            post_text="Looking for a design expert to join our core crew.",
            target_seniority="Associate / Junior Professional",
            max_yoe=2
        )
        self.assertFalse(fit)
        self.assertIn("seniority", reason.lower())

        # Junior role rejected if explicit YOE exceeds max_yoe
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Product Designer",
            post_text="Requires 8+ years experience in product design.",
            target_seniority="Associate / Junior Professional",
            max_yoe=2
        )
        self.assertFalse(fit)
        self.assertIn("yoe", reason.lower())

        # Junior role should be accepted
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Junior Product Designer",
            post_text="Great role for candidates with 1-2 years experience in design.",
            target_seniority="Associate / Junior Professional",
            max_yoe=2
        )
        self.assertTrue(fit)

    def test_mid_level_seniority_filter(self):
        # Mid-level target rejects Lead, Staff, Director
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Lead Product Designer",
            post_text="We are hiring a Lead to drive product vision.",
            target_seniority="Mid-Level Professional",
            max_yoe=5
        )
        self.assertFalse(fit)
        self.assertIn("seniority", reason.lower())

        # Director role should be disqualified
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Director of Design",
            post_text="Executive design leadership required.",
            target_seniority="Mid-Level Professional",
            max_yoe=5
        )
        self.assertFalse(fit)
        self.assertIn("seniority", reason.lower())

        # Mid-level role should be accepted
        fit, reason = JobParser.check_domain_and_yoe_fit(
            post_title="Product Designer",
            post_text="Looking for 3-4 years experience in Figma.",
            target_seniority="Mid-Level Professional",
            max_yoe=5
        )
        self.assertTrue(fit)

    def test_link_guard_profile_vs_post(self):
        # Profile URL without activity should NOT be set as post link
        card = MagicMock()
        text_el = MagicMock()
        text_el.inner_text.return_value = "We are hiring a Product Designer! Send resume to jobs@test.com"
        text_el.query_selector.return_value = None
        
        card.query_selector.side_effect = lambda sel: text_el if "update" in sel or "text" in sel else None
        card.inner_text.return_value = "We are hiring a Product Designer! Send resume to jobs@test.com"
        
        # Mock anchor tags: one is recruiter profile, no activity URN
        mock_a = MagicMock()
        mock_a.get_attribute.side_effect = lambda attr: "https://www.linkedin.com/in/jane-recruiter/" if attr == "href" else "Jane Recruiter"
        mock_a.inner_text.return_value = "Jane Recruiter"
        card.query_selector_all.return_value = [mock_a]

        res = JobParser.parse_post_card(card)
        self.assertIsNotNone(res)
        # Author profile URL should capture the profile
        self.assertEqual(res["author_profile_url"], "https://www.linkedin.com/in/jane-recruiter/")
        # Link should NOT be the /in/ recruiter profile URL
        self.assertNotEqual(res.get("link"), "https://www.linkedin.com/in/jane-recruiter/")

    def test_link_guard_with_activity_urn(self):
        # Activity link should be accepted
        card = MagicMock()
        text_el = MagicMock()
        text_el.inner_text.return_value = "We are hiring a Product Designer! Apply here jobs@test.com"
        text_el.query_selector.return_value = None
        
        card.query_selector.side_effect = lambda sel: text_el if "update" in sel or "text" in sel else None
        card.inner_text.return_value = "We are hiring a Product Designer! Apply here jobs@test.com"

        mock_a = MagicMock()
        mock_a.get_attribute.side_effect = lambda attr: "https://www.linkedin.com/feed/update/urn:li:activity:7123456789012345678/" if attr == "href" else "View Post"
        mock_a.inner_text.return_value = "View Post"
        card.query_selector_all.return_value = [mock_a]

        res = JobParser.parse_post_card(card)
        self.assertIsNotNone(res)
        self.assertIn("activity:7123456789012345678", res.get("link", ""))

if __name__ == "__main__":
    unittest.main()

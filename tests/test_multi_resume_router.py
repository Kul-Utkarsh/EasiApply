import unittest
import tempfile
import os
import shutil
from pathlib import Path
from src.api.server import (
    find_best_resume_for_job,
    list_all_resumes_meta,
    get_primary_resume_filename,
    save_user_profile,
    get_user_profile,
    RESUMES_DIR,
    PROFILE_PREFS_PATH
)
import src.api.server as server_module

class TestMultiResumeRouter(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.orig_resumes_dir = server_module.RESUMES_DIR
        self.orig_prefs_path = server_module.PROFILE_PREFS_PATH
        self.orig_resume_mgr = server_module.resume_mgr

        server_module.RESUMES_DIR = Path(self.temp_dir) / 'resumes'
        server_module.RESUMES_DIR.mkdir(parents=True, exist_ok=True)
        server_module.PROFILE_PREFS_PATH = Path(self.temp_dir) / 'user_profile.json'
        from src.utils.resume_manager import ResumeManager
        server_module.resume_mgr = ResumeManager(str(server_module.RESUMES_DIR))

    def tearDown(self):
        server_module.RESUMES_DIR = self.orig_resumes_dir
        server_module.PROFILE_PREFS_PATH = self.orig_prefs_path
        server_module.resume_mgr = self.orig_resume_mgr
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_multi_resume_routing_and_tags(self):
        res1 = server_module.RESUMES_DIR / 'Product_Design_Lead.md'
        res1.write_text("""# Alex River
Product Design Lead
Skills: Figma, Design Systems, UX/UI, Wireframing, Prototyping""", encoding='utf-8')

        res2 = server_module.RESUMES_DIR / 'UX_Researcher.md'
        res2.write_text("""# Alex River
Senior UX Researcher
Skills: User Research, Usability Testing, Field Interviews, Ethnography, Quantitative Surveys""", encoding='utf-8')

        server_module.save_user_profile({
            'primary_resume': 'Product_Design_Lead.md',
            'resume_tags': {
                'Product_Design_Lead.md': 'Product Designer',
                'UX_Researcher.md': 'UX Researcher'
            }
        })

        all_meta = server_module.list_all_resumes_meta()
        self.assertEqual(len(all_meta), 2)
        primary_item = next(r for r in all_meta if r['filename'] == 'Product_Design_Lead.md')
        self.assertTrue(primary_item['is_primary'])
        self.assertEqual(primary_item['role_tag'], 'Product Designer')

        match_ux = server_module.find_best_resume_for_job('Lead UX Researcher - B2B SaaS')
        self.assertIsNotNone(match_ux)
        self.assertEqual(match_ux[0], 'UX_Researcher.md')
        self.assertIn('User Research', match_ux[1])

        match_pd = server_module.find_best_resume_for_job('Senior Product Designer (Mobile & Web)')
        self.assertIsNotNone(match_pd)
        self.assertEqual(match_pd[0], 'Product_Design_Lead.md')
        self.assertIn('Design Systems', match_pd[1])

    def test_primary_resume_fallback_on_delete(self):
        res1 = server_module.RESUMES_DIR / 'Resume_A.md'
        res1.write_text("""# Candidate
Role A""", encoding='utf-8')
        res2 = server_module.RESUMES_DIR / 'Resume_B.md'
        res2.write_text("""# Candidate
Role B""", encoding='utf-8')

        server_module.save_user_profile({
            'primary_resume': 'Resume_A.md',
            'resume_tags': {'Resume_A.md': 'Role A', 'Resume_B.md': 'Role B'}
        })

        res = server_module.delete_resume('Resume_A.md')
        self.assertEqual(res['status'], 'deleted')

        profile = server_module.get_user_profile()
        self.assertNotIn('Resume_A.md', profile.get('resume_tags', {}))
        self.assertEqual(profile.get('primary_resume'), 'Resume_B.md')

if __name__ == '__main__':
    unittest.main()

import sys
sys.path.insert(0, ".")
from unittest.mock import MagicMock
from src.scraper.query_builder import LinkedInQueryBuilder
from src.scraper.parser import JobParser

# 1. Test Query Builder
q1, kw1 = LinkedInQueryBuilder.build_posts_search_query('Product Designer', location='Remote')
print("Q1:", q1)
print("KW1:", kw1)
assert 'Product Designer' in q1
assert 'hiring' in q1
assert 'product designer' in kw1

# 2. Test Multi-Role Query
q2, kw2 = LinkedInQueryBuilder.build_posts_search_query('Product Designer, UX Researcher')
print("Q2:", q2)
print("KW2:", kw2)
assert 'Product Designer' in q2
assert 'UX Researcher' in q2
assert 'ux researcher' in kw2

# Mock element generator
def make_mock_post(full_text, author='Jane Doe'):
    mock_el = MagicMock()
    mock_text_el = MagicMock()
    mock_text_el.query_selector.return_value = None
    mock_text_el.inner_text.return_value = full_text
    
    def q_sel(sel):
        if 'name' in sel:
            m = MagicMock()
            m.inner_text.return_value = author
            return m
        if 'text' in sel or 'description' in sel:
            return mock_text_el
        return None
    mock_el.query_selector.side_effect = q_sel
    mock_el.query_selector_all.return_value = []
    mock_el.inner_text.return_value = full_text
    mock_el.get_attribute.return_value = None
    mock_el.evaluate.return_value = None
    return mock_el

# 3. Test Candidate Post (#OpenToWork) -> Should return None
cand_post = make_mock_post("""
Hello network, I am #OpenToWork! Unfortunately I was recently laid off and am looking for my next role as a Product Designer. Please reach out if you know of any openings.
""")
r3 = JobParser.parse_post_card(cand_post, target_keywords=['product designer'])
assert r3 is None, f"Candidate post was not rejected! Got {r3}"

# 4. Test Milestone / Course Post -> Should return None
milestone_post = make_mock_post("""
Excited to share that I joined Acme Corp as a Product Designer! Grateful to everyone who supported my journey.
""")
r4 = JobParser.parse_post_card(milestone_post, target_keywords=['product designer'])
assert r4 is None, f"Milestone post was not rejected! Got {r4}"

# 5. Test Unrelated Role Hiring Post -> Should return None when target is Product Designer
unrelated_post = make_mock_post("""
We are hiring! Our restaurant is growing and we are looking to hire a Head Chef. Send your CV to chef@restaurant.com.
""")
r5 = JobParser.parse_post_card(unrelated_post, target_keywords=['product designer'])
assert r5 is None, f"Unrelated role post was not rejected! Got {r5}"

# 6. Test Genuine Target Hiring Post -> Should be ACCEPTED with parsed title
genuine_post = make_mock_post("""
We are hiring!
Role: Lead Product Designer
Our design team is expanding. If you love Figma and user research, apply here or email your resume to jobs@designfirm.com.
""")
res = JobParser.parse_post_card(genuine_post, target_keywords=['product designer'])
assert res is not None, "Genuine hiring post was rejected!"
print("Parsed Title:", res['title'])
print("Parsed Contact:", res['contact_info'])
assert res['title'] == 'Lead Product Designer', f"Expected Lead Product Designer, got {res['title']}"
assert 'jobs@designfirm.com' in res['contact_info'], f"Expected email, got {res['contact_info']}"

print("SUCCESS: ALL 6 TESTS PASSED PROPERLY!")

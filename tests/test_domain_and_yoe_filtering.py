import sys
sys.path.insert(0, '.')
from src.scraper.parser import JobParser
from src.api.server import extract_target_role_and_headline, get_user_profile, save_user_profile

# 1. Test YOE Extraction
assert JobParser.extract_yoe_from_text('Must have 10+ years of experience in product design') == 10
assert JobParser.extract_yoe_from_text('Minimum 8 years of experience required') == 8
assert JobParser.extract_yoe_from_text('Looking for someone with 1-2 years of experience') == 1
assert JobParser.extract_yoe_from_text('3-5 years in Figma') == 3
assert JobParser.extract_yoe_from_text('No specific years mentioned') is None

# 2. Test Seniority Extraction
assert JobParser.extract_seniority_from_title_and_text('VP of Product Design') == 'Director / Executive'
assert JobParser.extract_seniority_from_title_and_text('Principal Product Designer') == 'Staff / Principal'
assert JobParser.extract_seniority_from_title_and_text('Senior UX Designer') == 'Senior'
assert JobParser.extract_seniority_from_title_and_text('Associate Product Designer') == 'Junior / Entry'
assert JobParser.extract_seniority_from_title_and_text('Product Designer') == 'Mid-Level'

# 3. Test Experience & Seniority Gate
# Candidate has max 3 YOE -> 10+ YOE must be rejected
ok, reason = JobParser.check_domain_and_yoe_fit('Principal Designer', 'Requires 10+ years of experience', max_yoe=3)
assert not ok and 'YOE mismatch' in reason, f'Failed: {reason}'

# Candidate has max 3 YOE -> Director must be rejected
ok, reason = JobParser.check_domain_and_yoe_fit('Director of Product Design', 'Join our team', max_yoe=3)
assert not ok and 'Seniority mismatch' in reason, f'Failed: {reason}'

# 4. Test Universal Domain Disambiguation
# Digital UX candidate vs Industrial CAD post
digital_skills = ['Figma', 'UI', 'UX', 'Design Systems', 'Prototyping', 'Wireframing']
cad_exclude = ['CAD', 'SolidWorks', 'Manufacturing', 'Mechanical', 'Injection Molding']

ok, reason = JobParser.check_domain_and_yoe_fit(
    'Product Designer',
    'We need an injection molding SolidWorks CAD expert for automotive manufacturing.',
    domain_keywords=digital_skills,
    exclude_keywords=cad_exclude,
    max_yoe=3
)
assert not ok and 'Domain mismatch' in reason, f'Failed: {reason}'

# Digital UX candidate vs Figma SaaS post
ok, reason = JobParser.check_domain_and_yoe_fit(
    'Product Designer',
    'We are looking for a Product Designer with 1-2 years experience in Figma, design systems, and user research.',
    domain_keywords=digital_skills,
    exclude_keywords=cad_exclude,
    max_yoe=3
)
assert ok, f'Valid post was rejected: {reason}'

# 5. Test Resume Target Role Parsing (Anti-Inflation)
lines_junior = ['Alex Morgan', 'Product Designer specializing in 0 - 1 product development', 'contact@email.com']
role, headline = extract_target_role_and_headline(lines_junior, 'Product Designer | 1-2 years experience')
assert role == 'Product Designer', f'Expected Product Designer, got {role}'

lines_senior = ['Jane Doe', 'Senior Product Designer with 8 years building design systems', 'contact@email.com']
role_sr, _ = extract_target_role_and_headline(lines_senior, 'Senior Product Designer | 8 years')
assert role_sr == 'Senior Product Designer', f'Expected Senior Product Designer, got {role_sr}'

# 6. Test User Preferences Persistence with Multiple Target Roles & Locations (Isolated)
import tempfile
import pathlib
import src.api.server as server_module

temp_dir = tempfile.TemporaryDirectory()
orig_path = server_module.PROFILE_PREFS_PATH
server_module.PROFILE_PREFS_PATH = pathlib.Path(temp_dir.name) / "user_profile.json"

try:
    saved = save_user_profile({
        'target_role': 'Product Designer',
        'target_roles': ['Product Designer', 'UI/UX Designer', 'Interaction Designer'],
        'target_locations': ['Remote', 'San Francisco', 'Bangalore'],
        'max_yoe': 3
    })
    loaded = get_user_profile()
    assert loaded.get('target_role') == 'Product Designer'
    assert loaded.get('target_roles') == ['Product Designer', 'UI/UX Designer', 'Interaction Designer']
    assert loaded.get('target_locations') == ['Remote', 'San Francisco', 'Bangalore']
    assert loaded.get('max_yoe') == 3

    # Test ProfilePreferencesRequest parsing via FastAPI endpoint logic
    from src.api.server import ProfilePreferencesRequest, update_profile_prefs, get_profile_prefs
    req = ProfilePreferencesRequest(
        target_role='Product Designer, UI/UX Designer, Design Lead',
        target_locations=['Remote', 'New York'],
        max_yoe=3
    )
    res = update_profile_prefs(req)
    assert res['status'] == 'ok'
    prefs_res = get_profile_prefs()
    assert prefs_res['preferences']['target_role'] == 'Product Designer'
    assert 'UI/UX Designer' in prefs_res['preferences']['target_roles']
    assert 'Remote' in prefs_res['preferences']['target_locations']
finally:
    server_module.PROFILE_PREFS_PATH = orig_path
    temp_dir.cleanup()

print('ALL DOMAIN, YOE, MULTI-ROLE, AND LOCATION TESTS PASSED WITH 100% ACCURACY!')

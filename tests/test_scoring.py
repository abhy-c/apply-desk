from datetime import date
from job_app_system.models import Job,Contact
from job_app_system.scoring import score_job,score_contact

def job(title='Financial Analyst',location='London, UK',posted=None):
 return Job('1','Example',title,'https://example.com/job','test',posted,location,'hybrid',{'finance'},'analyst','open','Own forecasts')

def test_no_personal_defaults_or_unconfigured_role_results():
 assert not score_job(job(),None,date.today())['role_eligible']

def test_user_focus_allows_finance_and_non_us_roles():
 result=score_job(job(),None,date.today(),{'target_titles':'Financial Analyst','target_locations':'London','must_have':'finance'})
 assert result['role_eligible'] and result['role_score']>0
 assert not score_job(job('Product Manager'),None,date.today(),{'target_titles':'Financial Analyst'})['role_eligible']

def test_excluded_titles_are_user_defined():
 assert not score_job(job('Senior Financial Analyst'),None,date.today(),{'target_titles':'Financial Analyst','avoid':'Senior'})['role_eligible']

def test_missing_date_does_not_invent_a_freshness_requirement():
 assert score_job(job(),None,date.today(),{'target_titles':'Financial Analyst'})['role_eligible']

def test_company_level_contact_cannot_be_tier1():
 contact=Contact('1','Example','Person','Recruiter','person@example.com','verified','','company_level','','role','test','')
 assert score_contact(contact,{'role_score':90,'role_score_reasons':'high'})['outreach_tier']=='Tier 2 - dedicated domain'

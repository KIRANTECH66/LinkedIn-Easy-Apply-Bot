"""
Dry-run test for the agentic LinkedIn EasyApply Bot.

This test validates that:
1. All modules import without errors
2. All agents instantiate with valid config
3. The job database schema works
4. The config.yaml loads correctly
5. The flow can execute without real browser/API calls

Run: python3 test_dry_run.py
"""

import os
import sys
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_imports():
    """Test all modules import cleanly."""
    print("Testing imports...")

    # Core modules
    import easyapplybot
    import company_filler
    import ai_agent

    # Agents
    from agents import (
        ProfileAgent,
        JobDiscoveryAgent,
        JobMatchingAgent,
        ResumeIntelligenceAgent,
        ApplicationAgent,
        QuestionAgent,
        ApprovalAgent,
        TrackingAgent,
        LearningAgent,
        JobDatabase,
    )

    print("  ✓ All modules imported successfully")

def test_config_load():
    """Test config.yaml loads with all required keys."""
    print("Testing config.yaml...")

    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    required_keys = [
        "username", "password", "phone_number",
        "positions", "locations", "salary", "rate",
        "uploads", "output_filename", "ai"
    ]
    for key in required_keys:
        assert key in config, f"Missing required key: {key}"

    ai_keys = [
        "provider", "model", "anthropic_model",
        "scoring_threshold", "max_jobs_per_run", "batch_size",
        "human_approval", "review_file", "api_timeout_minutes",
        "recency_priority"
    ]
    for key in ai_keys:
        assert key in config["ai"], f"Missing ai key: {key}"

    print("  ✓ config.yaml has all required keys")

def test_profile_agent():
    """Test ProfileAgent instantiation."""
    print("Testing ProfileAgent...")

    import yaml
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    from agents.profile_agent import ProfileAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        profile_path = os.path.join(tmpdir, "test_profile.json")
        agent = ProfileAgent(profile_path=profile_path, config=config)
        profile = agent.get()

        assert "name" in profile
        assert "email" in profile
        assert "skills" in profile
        assert "preferred_roles" in profile
        assert profile["preferred_roles"] == config["positions"]
        assert profile["preferred_locations"] == config["locations"]

    print("  ✓ ProfileAgent works")

def test_job_database():
    """Test JobDatabase schema and CRUD."""
    print("Testing JobDatabase...")

    from agents.job_database import JobDatabase

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_jobs.db")
        db = JobDatabase(db_path)

        # Add a job
        db.add_job(
            job_id="12345",
            company="Test Corp",
            title="Software Engineer",
            location="Remote",
            description="Test job description",
            source="linkedin",
            url="https://linkedin.com/jobs/view/12345",
            salary="100000",
            decision="pending"
        )

        # Retrieve and verify
        job = db.get_job("12345")
        assert job is not None
        assert job["job_id"] == "12345"
        assert job["company"] == "Test Corp"
        assert job["decision"] == "pending"

        # Update job
        db.update_job("12345", decision="approved", match_score=0.85)
        job = db.get_job("12345")
        assert job["decision"] == "approved"
        assert job["match_score"] == 0.85

        # Query
        pending = db.get_pending_jobs()
        assert len(pending) == 0  # Now approved

        decided = db.get_decided_jobs()
        assert len(decided) == 1

    print("  ✓ JobDatabase works")

def test_ai_agent_config():
    """Test AIAgent and AgentConfig."""
    print("Testing AIAgent config...")

    from ai_agent import AIAgent, AgentConfig

    config = AgentConfig(
        provider="both",
        model="gpt-4o",
        anthropic_model="claude-sonnet-4",
        threshold=0.7,
        max_jobs=20,
        batch_size=10,
        human_approval=False,
        recency_priority=True,
    )

    agent = AIAgent(config=config, resume_text="Test resume")

    assert agent.config.threshold == 0.7
    assert agent.config.recency_priority is True
    assert agent.resume_text == "Test resume"

    print("  ✓ AIAgent config works")

def test_job_matching_agent():
    """Test JobMatchingAgent instantiation."""
    print("Testing JobMatchingAgent...")

    from agents.job_matching import JobMatchingAgent
    from ai_agent import AgentConfig

    config = AgentConfig(
        threshold=0.7,
        max_jobs=20,
        batch_size=10,
        recency_priority=True,
    )

    agent = JobMatchingAgent(config)
    assert agent.config.threshold == 0.7

    print("  ✓ JobMatchingAgent works")

def test_resume_intelligence_agent():
    """Test ResumeIntelligenceAgent instantiation."""
    print("Testing ResumeIntelligenceAgent...")

    from agents.resume_intelligence import ResumeIntelligenceAgent

    # Create a dummy resume text file
    with tempfile.NamedTemporaryFile(suffix=".txt", mode="w", delete=False) as f:
        f.write("Test resume content")
        resume_path = f.name

    try:
        agent = ResumeIntelligenceAgent(resume_path=resume_path)
        assert agent.resume_text == "Test resume content"
    finally:
        os.unlink(resume_path)

    print("  ✓ ResumeIntelligenceAgent works")

def test_approval_agent():
    """Test ApprovalAgent instantiation."""
    print("Testing ApprovalAgent...")

    from agents.approval import ApprovalAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        review_file = os.path.join(tmpdir, "review.md")
        agent = ApprovalAgent(
            review_file=review_file,
            human_approval=False,
            timeout_minutes=10,
        )

        # Test auto-approve
        from ai_agent import Job
        jobs = [
            Job(job_id="1", title="Engineer", company="A", location="Remote", description="Desc"),
            Job(job_id="2", title="Developer", company="B", location="Remote", description="Desc"),
        ]

        approved = agent.review(jobs)
        assert all(j.approved for j in approved)
        assert os.path.exists(review_file)

    print("  ✓ ApprovalAgent works")

def test_learning_agent():
    """Test LearningAgent instantiation."""
    print("Testing LearningAgent...")

    from agents.learning import LearningAgent

    with tempfile.TemporaryDirectory() as tmpdir:
        learning_file = os.path.join(tmpdir, "learning.json")
        output_file = os.path.join(tmpdir, "out.csv")

        # Create dummy output CSV
        with open(output_file, "w") as f:
            f.write("timestamp,jobID,job,company,attempted,result\n")
            f.write("2024-01-01 10:00:00,1,Engineer,CorpA,True,True\n")
            f.write("2024-01-02 10:00:00,2,Developer,CorpB,True,False\n")

        agent = LearningAgent(learning_file=learning_file, output_file=output_file)
        agent.learn_from_outcomes()

        # Verify learning file created
        assert os.path.exists(learning_file)

        # Check insights
        import json
        with open(learning_file) as f:
            insights = json.load(f)

        assert insights["total_applied"] == 2
        assert "CorpA" in insights["company_success_rate"]
        assert "CorpB" in insights["company_success_rate"]

    print("  ✓ LearningAgent works")

def test_company_filler_config():
    """Test CompanyFiller instantiation."""
    print("Testing CompanyFiller...")

    from company_filler import CompanyFiller

    # Mock browser and wait
    mock_browser = Mock()
    mock_wait = Mock()

    filler = CompanyFiller(
        browser=mock_browser,
        wait=mock_wait,
        config={"name": "Test", "email": "test@test.com", "phone": "123"},
        uploads={"Resume": "/fake/path.pdf"}
    )

    assert filler.config["name"] == "Test"
    assert "greenhouse" in filler.ATS_SIGNATURES

    print("  ✓ CompanyFiller works")

def test_dry_run_flow():
    """Test the full dry-run flow with mocked dependencies."""
    print("Testing full dry-run flow...")

    from agents.profile_agent import ProfileAgent
    from agents.job_database import JobDatabase
    from agents.job_matching import JobMatchingAgent
    from agents.resume_intelligence import ResumeIntelligenceAgent
    from agents.approval import ApprovalAgent
    from agents.tracking import TrackingAgent
    from agents.learning import LearningAgent
    from ai_agent import AgentConfig, Job

    with tempfile.TemporaryDirectory() as tmpdir:
        # Setup temp files
        profile_path = os.path.join(tmpdir, "profile.json")
        jobs_db_path = os.path.join(tmpdir, "jobs.db")
        learning_path = os.path.join(tmpdir, "learning.json")
        output_path = os.path.join(tmpdir, "out.csv")
        review_path = os.path.join(tmpdir, "review.md")
        resume_path = os.path.join(tmpdir, "resume.txt")

        with open(resume_path, "w") as f:
            f.write("Experienced Software Engineer\nSkills: Python, SQL, AWS")

        # Initialize all agents
        config = {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "555-1234",
            "salary": "100000",
            "positions": ["Software Engineer", "Backend Engineer"],
            "locations": ["Remote", "San Francisco"],
            "blacklist": ["BadCorp"],
            "blackListTitles": ["Sales"],
        }

        profile_agent = ProfileAgent(profile_path=profile_path, config=config)
        job_database = JobDatabase(jobs_db_path)
        matching_config = AgentConfig(
            threshold=0.7,
            max_jobs=5,
            batch_size=3,
            recency_priority=True,
        )
        job_matching = JobMatchingAgent(matching_config)
        resume_agent = ResumeIntelligenceAgent(resume_path=resume_path)
        approval_agent = ApprovalAgent(
            review_file=review_path,
            human_approval=False,
            timeout_minutes=1,
        )
        tracking_agent = TrackingAgent(output_path)
        learning_agent = LearningAgent(learning_path, output_path)

        # Simulate job discovery → add to database
        job_database.add_job(
            job_id="job_001",
            company="TechCorp",
            title="Senior Software Engineer",
            location="Remote",
            description="Python, AWS, 5+ years exp",
            source="linkedin",
            decision="pending"
        )

        job_database.add_job(
            job_id="job_002",
            company="BadCorp",  # Blacklisted
            title="Sales Engineer",
            location="Remote",
            description="Sales role",
            source="linkedin",
            decision="pending"
        )

        # Get pending jobs
        pending = job_database.get_pending_jobs()
        assert len(pending) == 2

        # Filter blacklisted (Profile Agent logic)
        profile = profile_agent.get()
        filtered = [
            j for j in pending
            if not profile_agent.is_company_blacklisted(j["company"])
            and not profile_agent.is_title_blacklisted(j["title"])
        ]
        assert len(filtered) == 1  # BadCorp + Sales filtered out

        # Convert to Job objects for matching
        jobs = [
            Job(
                job_id=j["job_id"],
                title=j["title"],
                company=j["company"],
                location=j["location"],
                description=j["description"],
            )
            for j in filtered
        ]

        # Score and filter
        scored = job_matching.match(jobs, profile, provider="openai")
        # Note: will score 0.0 without API key, but flow works

        # Resume evaluation (will use fallback without API)
        for job in jobs:
            evals = resume_agent.evaluate(job, provider="openai")
            job_database.update_job(
                job.job_id,
                recruiter_score=evals.get("recruiter", 0),
                hiring_manager_score=evals.get("hiring_manager", 0),
                ats_score=evals.get("ats", 0),
                composite_score=evals.get("composite", 0),
            )

        # Decision
        for job in jobs:
            job_record = job_database.get_job(job.job_id)
            if job_record and job_record.get("composite_score", 0) >= 0.7:
                job_database.update_job(job.job_id, decision="approved")
            else:
                job_database.update_job(job.job_id, decision="skipped")

        # Track
        tracking_agent.track("job_001", "Engineer", "TechCorp", True)

        # Learn
        learning_agent.learn_from_outcomes()

        # Verify learning file
        assert os.path.exists(learning_path)

    print("  ✓ Full dry-run flow works")

def main():
    """Run all tests."""
    print("=" * 50)
    print("DRY-RUN TESTS FOR LINKEDIN EASYAPPLY BOT")
    print("=" * 50)

    tests = [
        test_imports,
        test_config_load,
        test_profile_agent,
        test_job_database,
        test_ai_agent_config,
        test_job_matching_agent,
        test_resume_intelligence_agent,
        test_approval_agent,
        test_learning_agent,
        test_company_filler_config,
        test_dry_run_flow,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print("=" * 50)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 50)

    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
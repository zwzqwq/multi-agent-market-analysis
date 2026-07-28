import pytest
from src.api.store import ReportStore
import time

@pytest.fixture
def store():
    return ReportStore()

def test_create_and_get(store):
    report_id = store.create("test")
    assert report_id is not None
    report=store.get(report_id)
    assert report is not None
    assert report.topic == "test"
    assert report.status == "pending"

def test_get_nonexistent(store):
    report_id = "nonexistend"
    report=store.get(report_id)
    assert report is None
    
def test_update_running(store):
    report_id = store.create("test")
    before_status = store.get(report_id).status
    assert before_status == "pending"
    store.update_running(report_id)
    report=store.get(report_id)
    assert report.status == "running"

def test_list_recent(store):
    store.create("test1")
    time.sleep(0.1)
    store.create("test2")
    time.sleep(0.1)
    store.create("test3")
    recent = store.list_recent()
    assert len(recent) == 3
    assert recent[0].topic == "test3"
    assert recent[1].topic == "test2"
    assert recent[2].topic == "test1"

def test_list_recent_limit(store):
    store.create("test1")
    time.sleep(0.1)
    store.create("test2")
    time.sleep(0.1)
    store.create("test3")
    time.sleep(0.1)
    store.create("test4")
    time.sleep(0.1)
    store.create("test5")
    recent = store.list_recent(limit=4)
    assert len(recent) == 4
    assert recent[0].topic == "test5"
    assert recent[1].topic == "test4"
    assert recent[2].topic == "test3"
    assert recent[3].topic == "test2"



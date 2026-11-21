import datetime as dt
import json

import pytest

from daily_check import LAST_CHECK_STARTED_KEY, add_new_works, due_today, longest_waiting_first
from models import Paper

TODAY = dt.date(2026, 11, 22)


def make_paper(title, doi=None, failed_checks=0, last_check=None):
    return Paper(title=title, year=2000, doi=doi, pdf_urls=[], authors=["Immanuel Kant"],
                 failed_checks=failed_checks, last_check=last_check)


@pytest.mark.parametrize("failed_checks, days_ago, due", [
    (0, 0, True), (1, 0, False), (1, 1, True), (3, 3, False), (3, 4, True), (10, 29, False), (10, 30, True),
])
def test_the_wait_doubles_after_each_failed_check_up_to_a_month(failed_checks, days_ago, due):
    last_check = (TODAY - dt.timedelta(days=days_ago)).isoformat()
    assert due_today(make_paper("A", failed_checks=failed_checks, last_check=last_check), TODAY) is due


def test_the_authors_never_checked_go_first_then_the_longest_waiting(tmp_path):
    check_started = {"Kant": "2026-11-21T06:00:00", "Hegel": None, "Fichte": "2026-11-20T06:00:00", "Ross": None}
    lists = []
    for author, started in check_started.items():
        papers_file = tmp_path / author / "papers.json"
        papers_file.parent.mkdir()
        content = {"papers": [], LAST_CHECK_STARTED_KEY: started} if started else {"papers": []}
        papers_file.write_text(json.dumps(content), encoding="utf-8")
        lists.append(papers_file)

    order = [papers_file.parent.name for papers_file in longest_waiting_first(lists)]

    assert order == ["Hegel", "Ross", "Fichte", "Kant"]


def test_only_the_works_not_in_the_list_are_added():
    known = make_paper("Kritik der reinen Vernunft", doi="10.1/k")
    papers = [known]
    found = [make_paper("Kritik der reinen Vernunft", doi="10.1/K"), make_paper("Prolegomena", doi="10.1/p")]

    new = add_new_works(papers, found)

    assert [paper.title for paper in new] == ["Prolegomena"]
    assert len(papers) == 2

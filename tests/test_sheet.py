import sheet


class FakeSheet:
    def __init__(self, rows):
        self.rows = [sheet.HEADERS] + rows
        self.append_calls = 0

    def col_values(self, col):
        return [r[col - 1] for r in self.rows]

    @property
    def row_count(self):
        return 1000

    def get_all_values(self):
        return self.rows

    def update(self, rows, range_name, value_input_option=None):
        assert range_name == f"A{len(self.rows) + 1}"  # right below the last used row
        self.append_calls += 1
        self.rows.extend(rows)

    def get_all_records(self, expected_headers=None):
        return [dict(zip(self.rows[0], r)) for r in self.rows[1:]]


def row(link, status="New"):
    return ["2026-10-22", "src", "Job", "Co", link, "7", "why", status, ""]


def job(link, **extra):
    return {"source": "src", "title": "Job", "company": "Co", "link": link,
            "score": 8, "reason": "fit", **extra}


def test_get_existing_links_skips_header_and_normalizes():
    fake = FakeSheet([row("https://A.com/x/"), row("")])
    assert sheet.get_existing_links(fake) == {"https://a.com/x"}


def test_add_jobs_skips_duplicates_in_one_batch():
    fake = FakeSheet([row("https://a.com/1")])
    jobs = [job("https://a.com/1/"), job("https://a.com/2"), job("https://a.com/2"),
            job("https://a.com/3", date="2026-01-01")]

    added = sheet.add_jobs(jobs, fake)

    assert [j["link"] for j in added] == ["https://a.com/2", "https://a.com/3"]
    assert fake.append_calls == 1
    assert fake.rows[-1][0] == "2026-01-01"
    assert fake.rows[-1][7] == "New"


def test_add_jobs_no_new_jobs_makes_no_call():
    fake = FakeSheet([row("https://a.com/1")])
    assert sheet.add_jobs([job("https://a.com/1")], fake) == []
    assert fake.append_calls == 0


def test_get_approved():
    fake = FakeSheet([row("https://a.com/1"), row("https://a.com/2", " approved "),
                      row("https://a.com/3", "Rejected")])
    approved = sheet.get_approved(fake)
    assert [(r["Link"], r["row"]) for r in approved] == [("https://a.com/2", 3)]

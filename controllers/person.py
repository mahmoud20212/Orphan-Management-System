# ===== Person Controller =====
class PersonController:
    def __init__(self, db_service):
        self.db = db_service
        self.current_person = None
        self.current_type = None

    def set_person(self, person, person_type):
        self.current_person = person
        self.current_type = person_type

    def get(self):
        return self.current_person, self.current_type


class PaginationController:
    def __init__(self, per_page=100):
        self.page = 1
        self.per_page = per_page
        self.total = 0
        self.pages = 1

    def update(self, result):
        self.total = result["total"]
        self.pages = result["pages"]

    def next(self):
        if self.page < self.pages:
            self.page += 1

    def prev(self):
        if self.page > 1:
            self.page -= 1

from alfred3.condition import ListRandomizer

class GroupCounter(ListRandomizer):

    def __new__(cls, *args, **kwargs):
        return super(ListRandomizer, cls).__new__(cls)

    def __init__(self, matchmaker, abort_page = None):
        exp = matchmaker.exp
        n = matchmaker.max_groups
        randomizer_id = f"{matchmaker.matchmaker_id}_group_counter"
        session_ids = matchmaker.group.sessions if matchmaker.group is not None else None
        mode = matchmaker.max_groups_mode
        abort_page = abort_page if abort_page is not None else matchmaker.inactive_page
        respect_version=matchmaker.respect_version

        super().__init__(
            ("group_count", n),
            exp=exp,
            session_ids=session_ids,
            mode=mode,
            randomizer_id=randomizer_id,
            abort_page=abort_page,
            respect_version=respect_version
        )
    
    def count_group(self, raise_exception: bool = False):
        self.get_condition(raise_exception=raise_exception)

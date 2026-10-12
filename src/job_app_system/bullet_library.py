MESSAGE = 'Resume tailoring and bullet-library tools are not included in this public preview. Supply your own resume manually.'


def unavailable(*args, **kwargs):
    raise ValueError(MESSAGE)


create_proposal = draft_inventory = import_selected_drafts = library_state = review_bullets = review_proposal = unavailable

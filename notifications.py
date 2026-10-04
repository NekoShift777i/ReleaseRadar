from update_logic import UpdateResult



def get_pending_notifications(
        results: list[UpdateResult],
) -> list[UpdateResult]:
    return [
        result
        for result in results
        if result.notify_required
    ]
"""Compatibility import and command-line access to the original API client."""

from schoolmenu.provider import School, SchoolCafeClient

__all__ = ["School", "SchoolCafeClient"]

if __name__ == "__main__":
    from pprint import pprint

    pprint(SchoolCafeClient().get_weekly_menu())

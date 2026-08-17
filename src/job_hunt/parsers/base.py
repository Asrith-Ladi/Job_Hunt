"""Parser contract for an email alert source."""

from abc import ABC, abstractmethod


class AlertParser(ABC):
    source = "unknown"

    @abstractmethod
    def matches(self, message):
        """Return whether the message belongs to this source."""

    @abstractmethod
    def parse(self, message, observed_at):
        """Return normalized jobs and non-fatal warnings."""

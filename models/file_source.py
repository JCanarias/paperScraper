from abc import ABC, abstractmethod


class file_source(ABC):
    """ Retrieves files."""
    
    @abstractmethod
    def download(self, url: str):
        """Download the file."""
        
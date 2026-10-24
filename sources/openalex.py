import os
from dotenv import load_dotenv
import requests
import questionary
import nameparser
import pandas as pd
from datetime import date, datetime

from models import author
from models.author import Author
from models.text import Text
from .base import InformationSource

load_dotenv()

class OpenAlexSource(InformationSource):
    def __init__(self):
        """Session?"""
        self.BASE_URL: str | None = os.getenv("OPEN_ALEX_API_BASE_URL")
        self.API_KEY: str | None = os.getenv("OPEN_ALEX_API_KEY")
        self.ID_BASE_URL: str | None = os.getenv("OPEN_ALEX_BASE_ID_URL")
        self.DATABASE_PATH: str | None = os.getenv("WORKS_DATABASE_PATH")
        
    def _generate_text(self, result: dict, author: Author) -> Text:
        title: str = result["title"]
        open_alex_id: str = result["id"].rsplit("/", 1)[-1]
        doi: str = result["doi"]
        published: date = result["publication_date"].date()
        languages: list = list(result["language"])
        
        new_text = Text(
            title=title,
            author=author, # OJO, NO TIENE POR QUÉ SER EL AUTOR, PODRÍA SER TRADUCTOR, ETC
            open_alex_id=open_alex_id,
            doi=doi,
            published=published,
            languages=languages
        )
        
        return new_text
    
    def get_authors(self, query: str) -> list[Author]:
        return super().get_authors(query)
    
    def get_texts(self, query: str) -> list[Text]:
        return super().get_texts(query)
    
    def get_authors_texts(self, author: Author) -> list[Text]:
        url: str = "https://api.openalex.org/works"
        params: dict = {
            "api_key": self.API_KEY,
            "filter": f"authorships.author.id:{author.open_alex_id}"
            
        }
        response = requests.get(
            url = url,
            params = params
            )
        
        works_in_db: pd.DataFrame = pd.read_csv(filepath_or_buffer=self.DATABASE_PATH)
        downloaded_rows = works_in_db[works_in_db["downloaded"]]
        registered_isbns: list[str] = works_in_db["isbn"].dropna().to_list()
        registered_dois: list[str] = works_in_db["doi"].dropna().to_list()
        registered_dois: list[str] = works_in_db["issn"].dropna().to_list()
        
        # Create texts objects and checkbox options.
        # Check if texts are already in database or in calibre.
        found_texts: list[Text] = list()
        found_texts_titles: list[questionary.Choice] = list()
        for result in response.json()["results"]:
            new_text = self._generate_text(result, author)
            title: str = result["title"]
            open_alex_id: str = result["id"].rsplit("/", 1)[-1]
            doi: str = result["doi"]
            
            found_texts.append(new_text)
            found_texts_titles.append(result["title"])
            print(f"{result['publication_year']} - {result['title']}")
        
        return super().get_authors_texts(author)
    
    def identify_author(self) -> Author:
        search_input = input("Type in your author: ")
        params: dict = {
            "api_key": self.API_KEY,
            "search": search_input,
            "sort": "cited_by_count:desc"
            }
        response = requests.get(
            url = str(self.BASE_URL + "/authors"),
            params = params)
        results: dict = response.json()["results"]
                
        name_choices: list[questionary.Choice] = list()
        for result in results:
            name: str = result["display_name"]
            id: str = result["id"].rsplit("/", 1)[-1]
            new_choice = questionary.Choice(name, value = id)
            name_choices.append(new_choice)
        
        author_selection = questionary.select(
            message = "Which author did you mean?",
            choices = name_choices
        ).ask()
        
        identified_author_response: dict = {}
        for result in results:
            if result["id"] == f"{self.ID_BASE_URL}{author_selection}":
                identified_author_response = result
        
        full_name = nameparser.HumanName(identified_author_response["full_name"])
        identified_author = Author(
            name = str(full_name.first + full_name.middle),
            surnames = full_name.last_list,
            birth_date = None,
            death_date = None,
            birth_place = None,
            death_place = None,
            open_alex_id = identified_author_response["id"].rsplit("/", 1)[-1],
            orcid = None
        )
        
        print(f"selected author: {author_selection}")
        return identified_author
        
    
    def search_by_author(self) -> list[Text]:
        author = self.identify_author()
        texts = self.get_authors_texts(author = author)
        print(author)

import questionary

from sources.base import InformationSource
from sources.openalex import OpenAlexSource

def selected_database(choice):
    if choice == "open_alex_choice":
        source = OpenAlexSource()
        return source

def main() -> None:
    # Search source selection.
    chosen_database = questionary.select(
        message = "Which database do you want to use?",
        choices = [
            questionary.Choice("Open Alex", value = "open_alex_choice")
        ] # Should be generated from all the possible sources dinamically.
    ).ask()
    
    method_choice = questionary.select(
        message = "How do you want to search?",
        choices=[
            questionary.Choice("By author", value = "author"),
            questionary.Choice("By title", value = "title")
        ]
    ).ask()
    
    print(f'Chosen database: {chosen_database}\nChosen search method: {method_choice}')
    
    database: InformationSource = selected_database(choice = chosen_database)
    if method_choice == "author":
        database.search_by_author()
    
main()

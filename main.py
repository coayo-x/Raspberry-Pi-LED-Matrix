from db_manager import init_db
from rotation_engine import get_today_category, get_today_pokemon_id
from apis.pokemon import get_pokemon_data


def main():
    init_db()

    category = get_today_category()
    print(f"Today's category: {category}")

    if category == "pokemon":
        pokemon_id = get_today_pokemon_id()

        # DEBUG: نطبع الرقم لمعرفة ماذا يطلب البرنامج
        print(f"DEBUG pokemon_id: {pokemon_id}")

        pokemon = get_pokemon_data(pokemon_id)

        print(f"Today's Pokémon is: {pokemon['name']}")
        print(f"Types: {' / '.join(pokemon['types'])}")
        print(f"HP: {pokemon['hp']} | ATK: {pokemon['attack']} | DEF: {pokemon['defense']}")
        print(f"Height: {pokemon['height']} | Weight: {pokemon['weight']}")
        print(f"Image URL: {pokemon['image_url']}")
    else:
        print("Pokémon is not the selected category today.")


if __name__ == "__main__":
    main()
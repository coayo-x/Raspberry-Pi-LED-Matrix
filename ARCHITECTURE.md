## Goal

Build an LED display system that shows different content every day using a rotation system with no repetition.

---

## Core Rules

- Each day, the system displays a different category.
- Category order is randomized with no repetition until the full cycle is completed.

### Pokémon

- Randomized order (shuffle once per cycle).
- No repetition until all Pokémon have been shown.

### Jokes

- Same logic as Pokémon.
- Randomized cycle with no repetition until completion.

### Weather & Temperature

- Live API data.
- No rotation storage required.

### Database

- SQLite is the single source of truth.
- The system updates only once per day.

hi lol

"""
MCP Server — TheMealDB Recipe Tools
Exposes 4 tools that any MCP agent can call to search and fetch recipes.

Run locally:   mcp dev meals_server.py
Connect any MCP client: add entry to mcp_config.json (see README)

IMPORTANT: This server uses STDIO transport.
           Never write to stdout — it corrupts the JSON-RPC stream.
           All logging goes to stderr.
"""

import sys
import logging
import httpx
from mcp.server.fastmcp import FastMCP

# ── Logging (stderr only — NEVER stdout for STDIO servers) ──────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("meals-mcp")

# ── MCP Server instance ─────────────────────────────────────────────────
mcp = FastMCP("meals")

BASE_URL = "https://www.themealdb.com/api/json/v1/1"


# ── Helper ──────────────────────────────────────────────────────────────

def fetch(path: str, params: dict = None) -> dict:
    """Make a GET request to TheMealDB and return parsed JSON."""
    url = f"{BASE_URL}/{path}"
    logger.info("GET %s params=%s", url, params)
    response = httpx.get(url, params=params, timeout=10)
    response.raise_for_status()
    return response.json()


def parse_ingredients(meal: dict) -> list[dict]:
    """Extract the ingredient/measure pairs from a meal object."""
    ingredients = []
    for i in range(1, 21):
        name    = meal.get(f"strIngredient{i}", "").strip()
        measure = meal.get(f"strMeasure{i}", "").strip()
        if name:
            ingredients.append({"name": name, "measure": measure})
    return ingredients


# ── Tool 1: search_meals_by_name ────────────────────────────────────────

@mcp.tool()
def search_meals_by_name(query: str, limit: int = 5) -> list[dict]:
    """
    Search meals by name.

    Args:
        query: The meal name to search for (e.g. "pasta", "chicken curry").
        limit: Max number of results to return (1–25, default 5).

    Returns a list of meals with id, name, area, category, and thumbnail.
    """
    limit = max(1, min(limit, 25))
    data = fetch("search.php", {"s": query})

    meals = data.get("meals")
    if not meals:
        logger.info("No meals found for query '%s'", query)
        return [{"message": f"No meals found for '{query}'"}]

    results = []
    for meal in meals[:limit]:
        results.append({
            "id":       meal["idMeal"],
            "name":     meal["strMeal"],
            "area":     meal.get("strArea", ""),
            "category": meal.get("strCategory", ""),
            "thumb":    meal.get("strMealThumb", ""),
        })

    logger.info("Returning %d meals for query '%s'", len(results), query)
    return results


# ── Tool 2: meals_by_ingredient ─────────────────────────────────────────

@mcp.tool()
def meals_by_ingredient(ingredient: str, limit: int = 12) -> list[dict]:
    """
    Filter meals by a main ingredient.

    Args:
        ingredient: The ingredient to filter by (e.g. "chicken", "salmon").
        limit: Max number of results (default 12).

    Returns a list with id, name, and thumbnail for each meal.
    """
    data = fetch("filter.php", {"i": ingredient})

    meals = data.get("meals")
    if not meals:
        logger.info("No meals found for ingredient '%s'", ingredient)
        return [{"message": f"No meals found with ingredient '{ingredient}'"}]

    results = []
    for meal in meals[:limit]:
        results.append({
            "id":    meal["idMeal"],
            "name":  meal["strMeal"],
            "thumb": meal.get("strMealThumb", ""),
        })

    logger.info("Returning %d meals for ingredient '%s'", len(results), ingredient)
    return results


# ── Tool 3: meal_details ────────────────────────────────────────────────

@mcp.tool()
def meal_details(id: str) -> dict:
    """
    Get full details for a specific meal by its ID.

    Args:
        id: The TheMealDB meal ID (e.g. "52772").

    Returns full meal info including instructions, ingredients, and measures.
    """
    data = fetch("lookup.php", {"i": str(id)})

    meals = data.get("meals")
    if not meals:
        logger.info("No meal found for id '%s'", id)
        return {"message": f"No meal found with id '{id}'"}

    meal = meals[0]
    result = {
        "id":           meal["idMeal"],
        "name":         meal["strMeal"],
        "category":     meal.get("strCategory", ""),
        "area":         meal.get("strArea", ""),
        "instructions": meal.get("strInstructions", ""),
        "image":        meal.get("strMealThumb", ""),
        "source":       meal.get("strSource", ""),
        "youtube":      meal.get("strYoutube", ""),
        "ingredients":  parse_ingredients(meal),
    }

    logger.info("Returning details for meal '%s'", result["name"])
    return result


# ── Tool 4: random_meal ─────────────────────────────────────────────────

@mcp.tool()
def random_meal() -> dict:
    """
    Fetch one random meal with full details (ingredients, instructions, etc.).

    Returns the same shape as meal_details.
    """
    data = fetch("random.php")

    meals = data.get("meals")
    if not meals:
        return {"message": "Could not retrieve a random meal. Try again."}

    meal = meals[0]
    result = {
        "id":           meal["idMeal"],
        "name":         meal["strMeal"],
        "category":     meal.get("strCategory", ""),
        "area":         meal.get("strArea", ""),
        "instructions": meal.get("strInstructions", ""),
        "image":        meal.get("strMealThumb", ""),
        "source":       meal.get("strSource", ""),
        "youtube":      meal.get("strYoutube", ""),
        "ingredients":  parse_ingredients(meal),
    }

    logger.info("Returning random meal '%s'", result["name"])
    return result


# ── Entry point ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()

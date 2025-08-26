#!/usr/bin/env python3
"""
Category Spending Analysis Script

Usage:
    python analyze_category.py --budget main --category "Gasoline" --period "last_month"
"""

import argparse
import sys

from src.workflows.category_analyzer import analyze_category_spending


def main():
    parser = argparse.ArgumentParser(
        description="Analyze spending in a specific YNAB category over a time period"
    )
    parser.add_argument(
        "--budget",
        required=True,
        choices=["main", "secondary"],
        help="Budget to analyze (main or secondary)",
    )
    parser.add_argument(
        "--category", required=True, help="Category name to analyze (e.g., 'Gasoline')"
    )
    parser.add_argument(
        "--period",
        required=True,
        choices=["last_month", "current_month", "ytd"],
        help="Time period to analyze",
    )

    args = parser.parse_args()

    try:
        total_spent = analyze_category_spending(args.budget, args.category, args.period)
        print(
            f"Total spent on '{args.category}' in {args.budget} budget during {args.period}: ${total_spent:.2f}"
        )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

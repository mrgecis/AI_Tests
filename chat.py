#!/usr/bin/env python3
"""
Interactive Financial Chatbot powered by Claude and Financial Modeling Prep API.

Chat with Claude about company debt trends and financial data.
"""

import os
import sys
from dotenv import load_dotenv
from financial_chatbot import FinancialChatbot


def load_keys() -> tuple:
    """Load API keys from environment."""
    load_dotenv()
    fmp_key = os.getenv('FMP_API_KEY')
    claude_key = os.getenv('CLAUDE_API_KEY')

    if not fmp_key:
        print("Error: FMP_API_KEY not found in .env")
        sys.exit(1)

    if not claude_key:
        print("Error: CLAUDE_API_KEY not found in .env")
        print("\nAdd your Claude API key to .env:")
        print("  CLAUDE_API_KEY=your_key_here")
        print("\nGet your key at: https://console.anthropic.com/account/keys")
        sys.exit(1)

    return fmp_key, claude_key


def print_welcome():
    """Print welcome message."""
    print("\n" + "=" * 70)
    print("💬 FINANCIAL CHATBOT - Powered by Claude & Financial Modeling Prep")
    print("=" * 70)
    print("\nAsk me about company debt trends and financial data!")
    print("\nExamples:")
    print("  - Which companies have increasing debt?")
    print("  - Compare Tesla and Nvidia debt trends")
    print("  - Is Apple's debt increasing or decreasing?")
    print("  - Show me companies with the highest debt growth")
    print("\nCommands:")
    print("  'companies' - Show analyzed companies")
    print("  'reset'     - Reset conversation history")
    print("  'quit'      - Exit the chatbot")
    print("=" * 70 + "\n")


def main():
    """Main chatbot loop."""
    fmp_key, claude_key = load_keys()

    print("Initializing chatbot...")
    chatbot = FinancialChatbot(fmp_key, claude_key)

    print_welcome()

    while True:
        try:
            user_input = input("You: ").strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.lower() == 'quit':
                print("\nGoodbye!")
                break
            elif user_input.lower() == 'reset':
                chatbot.reset_conversation()
                continue
            elif user_input.lower() == 'companies':
                chatbot.show_analyzed_companies()
                continue

            # Get response from Claude
            print("\nClaude: ", end="", flush=True)
            response = chatbot.chat(user_input)
            print(response)
            print()

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\nError: {e}")
            print("Please try again.\n")


if __name__ == "__main__":
    main()

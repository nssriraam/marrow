# Contributing to Marrow

Thank you for your interest in contributing to Marrow! We welcome pull requests from the community.

## Development Environment Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/nssriraam/marrow.git
   cd marrow
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables:**
   Copy `.env.example` to `.env` and configure your API keys (specifically the Fireworks AI key if you intend to test the live inference engine).

## Contribution Guidelines

* **Code Style:** We follow standard PEP 8 conventions. Please ensure your code is clean and well-documented.
* **Pull Requests:** When submitting a PR, provide a clear description of the problem you are solving or the feature you are adding.
* **Testing:** Ensure that the fallback deterministic reasoner still works if API keys are not provided.

## Bug Reports and Feature Requests

If you encounter an issue or have a feature idea, please open an issue on GitHub with a detailed description.

Thank you for helping make cloud orchestration smarter!

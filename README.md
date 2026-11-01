# 💸 AI Expense Analyzer

An AI-powered personal finance management web application built with **Python, Streamlit, SQLite, Pandas, Plotly** and an **LLM (Gemini or OpenAI)**.

## 🚀 Key Features

- **Expense Management**: Add, edit, and delete expenses; automatic AI or keyword-based categorization.
- **Bank Statement Import**: Upload CSV or Excel bank statements with auto-column detection and duplicate prevention.
- **Interactive Dashboard**: Total spend, savings calculation, spending by category (pie chart), monthly comparison (bar chart), daily trends, and stacked category breakdown.
- **Budgets & Savings**: Set monthly income, define category budgets, auto-calculate recommended budgets, forecast next-month spending, and generate custom AI savings plans.
- **AI Financial Assistant**: Conversational assistant grounded purely on your actual database numbers.
- **AI Expense Analysis**: Detect unusual transactions (outliers), repeated expenses/merchants, and month-over-month category trends.
- **Reports**: Comprehensive monthly summaries, budget vs. actual breakdowns, and instant PDF/CSV export.

---

## 🛠️ Quick Start

### 1. Set Up Environment

Run in the project directory:

```bash
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1   # PowerShell
# or: venv\Scripts\activate.bat  # Command Prompt

# Install required dependencies
pip install -r requirements.txt
```

### 2. Configure LLM (Optional)

Copy `.env.example` to `.env` and configure your API key (if using Gemini or OpenAI):

```bash
# In .env:
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
```

> **Note**: Even without an API key, the application works completely using keyword-based categorization and pandas-powered computations! AI insights and assistant chatbot will become active once an API key is provided.

### 3. Launch the Application

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## 📁 Project Structure

```
ai-expense-analyzer/
├── app.py                     # Main Streamlit web application
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables & API keys
├── .env.example               # Template environment configuration
├── core/
│   ├── __init__.py
│   ├── db.py                  # SQLite database queries & schema
│   ├── llm.py                 # LLM provider interface & rule-based fallback
│   ├── importer.py            # CSV/Excel statement parser & normalizer
│   ├── analytics.py           # Pandas-based math, trends & anomaly detection
│   └── reports.py             # PDF and CSV report generator
├── sample_data/
│   └── sample_statement.csv   # Ready-to-import sample bank statement
└── data/
    └── expenses.db            # SQLite database (auto-generated)
```

## 🔒 Privacy & Accuracy Guarantee

1. **Local Storage**: Your raw transactions remain stored in your local SQLite database (`data/expenses.db`).
2. **Deterministic Calculations**: All math and aggregations are strictly computed by Pandas and NumPy; the LLM is only used for explanation and categorization.

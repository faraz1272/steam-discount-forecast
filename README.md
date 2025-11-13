# **WaitForIt - Price Drop Incoming?**
### *Never overpay for a game again.*

---

<p align="center">
  <img src="images/homepage.png" alt="WaitForIt Homepage" width="700"/>
</p>

---

## 🎮 **Why I Built WaitForIt**

I still remember the launch of **Starfield**.  
As a long-time Bethesda fan who poured hundreds of hours into *Skyrim*, I pre-ordered it the moment it went live, full price, day one. I played it nonstop and loved it.

But two weeks later, the price dropped.

Not because the game was bad, but because I bought it at the wrong **time**.  
That stung far more than I expected.

Fast forward three years.  
While studying **Data Science & AI**, that memory kept resurfacing. I began wondering whether other gamers faced the same problem, and a quick dive into **Reddit threads**, **YouTube comments**, and **review sites** made one thing clear:

**Everyone hates missing a sale.**

That’s when the idea became obvious:

> _What if you could predict when a game will get its first discount?_

That idea turned into **WaitForIt** - a machine-learning powered companion that helps gamers decide whether to **buy now** or **wait for a price drop**.

- **Live Service:** https://waitforit-service-417869241340.europe-west2.run.app


> **Note:** This project is an ongoing effort and will be updated frequently as new features, improvements, and models are added.
---

## 🚀 **What WaitForIt Does**

- Predicts the **probability of a discount** in the next **30 or 60 days**
- Learns from historical price data, publisher behaviour, genre patterns, and launch dynamics
- Surfaces insights via a fast **REST API**
- Helps gamers **avoid overpaying** and make smarter buying decisions

---

## 🧠 **How It Works (Short Version)**

- Data sourced from **Steam** & **ITAD APIs**
- Cleaned and organized into a SQL warehouse
- Feature engineering on:
  - price history  
  - early-launch behaviour  
  - review & publisher signals  
  - seasonal sale effects  
- Trained **LightGBM** models for 30-day and 60-day discount prediction
- Served using **FastAPI**, containerized in **Docker**, deployed on **Cloud Run**

---

## 🔧 **API Usage**

### **Predict Discount Probability**
`POST /predict`

**Request**
```json
{
  "app_id": 123456
}

**Response**
```json
{
  "prob_30d": 0.72,
  "prob_60d": 0.91,
  "decision": "Likely to discount — Wait"
}

## 🛠 Tech Stack
- Python (LightGBM, Pandas, Scikit-learn)
- FastAPI
- Docker & Google Cloud Run
- SQL (PostgreSQL)
- GitHub Actions (CI/CD)
- Cloud Storage for model artifacts

---

## 📈 Live Demo / Service Links


---

## 📅 Roadmap
- Add SHAP-based explanation insights  
- Build a browser extension (“Should I wait?” bubble on Steam pages)  
- Add personalized user watchlists  
- Expand predictions to Epic, PSN, and Xbox Store  
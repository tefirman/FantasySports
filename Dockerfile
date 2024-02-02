
FROM python:3.10
RUN pip install numpy pandas wget yahoo_oauth yahoo_fantasy_api python-dotenv \
    XlsxWriter geopy matplotlib beautifulsoup4 Unidecode black lxml scipy pdoc


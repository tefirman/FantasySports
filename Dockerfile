
FROM python:3.10
LABEL org.opencontainers.image.source=https://github.com/tefirman/FantasySports
LABEL org.opencontainers.image.description="Container image corresponding to Taylor Firman's FantasySports repository"
LABEL org.opencontainers.image.licenses=MIT
RUN pip install numpy pandas wget yahoo_oauth yahoo_fantasy_api python-dotenv \
    XlsxWriter geopy matplotlib beautifulsoup4 Unidecode black lxml scipy pdoc


FROM homenasbot-base:latest

COPY bot/ /app/bot/

WORKDIR /app/

CMD ["python3", "-m", "bot"]

FROM python:3.22

WORKDIR /app

COPY . .

RUN pip install -r requirements.txt


CMD ["python", "bot.py"]

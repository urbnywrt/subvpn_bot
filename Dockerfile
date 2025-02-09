FROM python:3.11

WORKDIR /app

COPY . .
RUN apt-get update && apt-get install nano git -y
RUN pip install -r requirements.txt

CMD ["python", "bot.py"]

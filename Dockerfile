FROM python:3.11

WORKDIR /app

COPY . .
RUN apt-get update && apt-get install nano git -y
RUN pip install -r requirements.txt
RUN git clone https://github.com/mewhrzad/marzpy.git /app/marzpy
RUN mv -r /app/marzpy/marzpy/marzpy/api/ /usr/local/lib/python3.11/site-packages/marzpy/api/

CMD ["python", "bot.py"]

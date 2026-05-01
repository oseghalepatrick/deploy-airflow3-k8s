FROM apache/airflow:3.2.0-python3.11

COPY ./dags/ /opt/airflow/dags/

COPY ./requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

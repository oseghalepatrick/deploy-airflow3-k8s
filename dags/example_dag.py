import time
import datetime
from airflow.sdk import task, dag

@dag(
    start_date=datetime.datetime(2021, 1, 1),
    schedule="@daily"
)
def example_dag():
    @task
    def hello_world():
        time.sleep(5)
        print("Hello world, from Airflow!")
    
    # @task
    # def new_world():
    #     time.sleep(5)
    #     print("Welcome to the new world, from Airflow!")
    
    @task
    def goodbye_world():
        time.sleep(5)
        print("Goodbye world, from Airflow!")
    
    # hello_world() >> new_world() >> goodbye_world()
    hello_world() >> goodbye_world()
example_dag()
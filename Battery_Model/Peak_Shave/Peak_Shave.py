# ECE 584 -- Taylor Sprinkle
# Algorithm for load peak shaving
# Dev Branch File

# read in load data csv file
import csv;

# read in hourly data into an array
with open('dp_data_hourly.csv') as hourly_data:
    data = list(csv.reader(hourly_data));

# print items in list
for list in data:
    print(list);
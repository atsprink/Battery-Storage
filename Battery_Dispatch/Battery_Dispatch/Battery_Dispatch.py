# Import python modules
import csv
import sys
import copy

# Open load data file and create new battery dispatch file
with open('Load_Data.csv') as Load_Data_Temp:
    Load_Data = list(csv.reader(Load_Data_Temp));
with open('PV_Output_Data.csv') as PV_Data_Temp:
    PV_Data = list(csv.reader(PV_Data_Temp));

# System Parameters
BESS_Capacity = 10000000         # In [Wh]
State_of_Charge = .80            # In %
MDOD = .80                       # In % of total capacity
Efficiency = 0.85                # BESS total round trip efficiency
Excess_Threshold = 5500000       # In Watts

# Function to calculate PV and Load kWh Forecast
def Energy_Forecast(Demand_Data, index, threshold, days):
    # Reset forecasts and jump index one day ahead
    kWh_Forecast = 0
    index = index
    # Calculate total kWh for next 48 hours
    # initialize temporary variables
    index_temp = index
    row = index
    for row in Demand_Data[index:(index+(days*24+1))]:
        # Increment hour
        index_temp = index_temp + 1
        # Get system load in Watts for current hour and next hour
        Hour_One_Load = int(row[4])
        Hour_Two_Load = int(Demand_Data[index_temp][4])
        # Check if demand exceeds peak, and calculate area of trapezoid
        if Hour_One_Load >= threshold or Hour_Two_Load >= threshold:
            kWh_Forecast = kWh_Forecast + (1/2)*((Hour_One_Load-threshold) + (Hour_Two_Load-threshold))
    return kWh_Forecast

# Function to charge BESS
def Charge(PV_Data, BESS_Dispatch, State_of_Charge, Hour):
    # Temporary index variable
    index_temp = Hour
    for row in PV_Data[Hour:Hour+25]:
        # Charging BESS off PV
        BESS_Dispatch[index_temp][4] = int(row[4])
        index_temp = index_temp + 1
    return BESS_Dispatch

# Function to charge and discharge BESS
def Charge_Discharge(PV_Data, Demand_Data, BESS_Dispatch, State_of_Charge, Excess_Threshold, Hour):
    # Temporary index variable
    index_temp = Hour
    for row in Demand_Data[Hour:Hour+25]:
        if int(row[4]) >= Excess_Threshold:
            BESS_Dispatch[index_temp][4] = -1*(int(row[4]) - Excess_Threshold)
        else:
            BESS_Dispatch[index_temp][4] = int(PV_Data[index_temp][4])
        index_temp = index_temp + 1
    return BESS_Dispatch


# Function to update BESS SOC
def Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour):
    # Temporary index variable
    kWh_Charge = 0
    index_temp = Hour
    for row in BESS_Dispatch[Hour:Hour+25]:
        index_temp = index_temp + 1
        # Get kW charge for current and next hour
        Hour_One_Power = int(row[4])
        Hour_Two_Power = int(BESS_Dispatch[index_temp][4])
        # Calculate area under this curve
        kWh_Charge = (1/2)*(Hour_One_Power + Hour_Two_Power)
        # Update State of charge
        State_of_Charge = State_of_Charge + kWh_Charge/BESS_Capacity
        # If max SOC is reached, stop charging.  If MDOD is reached, stop discharging
        if State_of_Charge >= 1.0 and int(BESS_Dispatch[index_temp][4]) >= 0:
            State_of_Charge = 1.0
            BESS_Dispatch[index_temp][4] = 0
        if State_of_Charge <= (1-MDOD) and int(BESS_Dispatch[index_temp][4]) < 0:
            State_of_Charge = 1.0-MDOD
            BESS_Dispatch[index_temp][4] = 0
        # Update time-series SOC data
        State_of_Charge_Monitor[index_temp][4] = State_of_Charge
    return State_of_Charge


# Initialize variables
Hour = 0
Day = 1
BESS_Dispatch = copy.deepcopy(PV_Data)
State_of_Charge_Monitor = copy.deepcopy(PV_Data)
State_of_Charge_Monitor[0][4] = State_of_Charge
dispatching = True
while dispatching:

    # Get peak load and PV output forecasts for next 24 hours
    Peak_Load_kWh_Forecast = Energy_Forecast(Load_Data, Hour, Excess_Threshold, 1)
    PV_kWh_Forecast = Energy_Forecast(PV_Data, Hour, 0, 1)

    Battery_Capacity = BESS_Capacity*State_of_Charge

    # Check forecast for peak load to shave
    if Peak_Load_kWh_Forecast == 0:
        # If no peak load, no discharging, so charge batteries
        BESS_Dispatch = Charge(PV_Data, BESS_Dispatch, State_of_Charge, Hour)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour)
    else:
        # If there is peak load, the dispatch will be a combination of charging and discharging
        BESS_Dispatch = Charge_Discharge(PV_Data, Load_Data, BESS_Dispatch, State_of_Charge, Excess_Threshold, Hour)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour)

    # Check for end of data and increment day
    if Day == 242:
        dispatching = False
    Day = Day + 1
    Hour = Hour + 24

# Write dispatch and state of charge to output csv file
Battery_Dispatch = open('Battery_Dispatch.csv', 'w')
Battery_Dispatch_Writer = csv.writer(Battery_Dispatch)
for row in BESS_Dispatch:
    Battery_Dispatch_Writer.writerow(row)
    
Battery_Dispatch.close()

SOC = open('State_of_Charge.csv', 'w')
State_of_Charge_Writer = csv.writer(SOC)
for row in State_of_Charge_Monitor:
    State_of_Charge_Writer.writerow(row)
SOC.close()





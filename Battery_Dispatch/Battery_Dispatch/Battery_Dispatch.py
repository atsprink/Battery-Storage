# v1.12.4 Corrected loss calculation again
# ---------------------------- Input -------------------------------- #
# Import python modules
import csv
import copy
import math


# Open load data file and create new battery dispatch file
with open('Load_Data.csv') as Load_Data_Temp:
    Load_Data = list(csv.reader(Load_Data_Temp));
with open('PV_Output_Data.csv') as PV_Data_Temp:
    PV_Data = list(csv.reader(PV_Data_Temp));

# System Parameters
BESS_Capacity = 10000000            # In [Wh]
Warranty_Gaurantee = 1.0            # Minimum system capacity guaranteed by BESS warranty in % of rated capacity
BESS_Capacity_Increase = 0          # Increase the BESS Capacity each year via modular units
BESS_Capacity_Increase_Freq = 1     # Interval for increase BESS capacity
State_of_Charge = .80               # In %
MDOD = .80                          # In % of total capacity
Efficiency = 0.85                   # BESS total round trip efficiency
One_Way_Eff = math.sqrt(Efficiency) # One way efficiency
Excess_Threshold = 5500000          # In Watts
Simulation_Duration = 1             # Years for simulation to run
Load_Growth = 0.01                  # % load growth per year
BESS_Degredation = 0.03             # % battery degradation per year
Forecast_Accuracy_Factor = 1        # Tune this and the factor below to improve peak shave results after load growth and degradation
Forecast_Accuracy_Factor_Annual_Growth = 0.055 # Accuracy forecast factor increase by this amount each year
Sbase = 15000000                    # Power base for system.  Chosen to be equal to the substation xfmr rating
# ------------------------------------------------------------------- #

# -------------------------- Functions ------------------------------ #
# Function to calculate PV and Load kWh Forecast
def Energy_Forecast(Demand_Data, hour, threshold, days):
    # Reset forecasts and jump index one day ahead
    kWh_Forecast = 0
    # initialize temporary variables and check for last day of year to loop load data to beginning of year
    if  hour == len(Demand_Data) - (days*24+1):
        hour = 0
    index_temp = hour + (days*24)
    row = hour
    for row in Demand_Data[(hour+(days*24)):(hour+((days+1)*24+1))]:
        # Increment hour
        index_temp = index_temp + 1
        if index_temp >= len(Demand_Data):
            index_temp = 0
        # Get system load in Watts for current hour and next hour
        Hour_One_Load = float(row[4])
        Hour_Two_Load = float(Demand_Data[index_temp][4])
        # Check if demand exceeds peak, and calculate area of trapezoid
        if Hour_One_Load >= threshold or Hour_Two_Load >= threshold:
            kWh_Forecast = kWh_Forecast + integrate(Hour_One_Load, Hour_Two_Load, threshold)
    return kWh_Forecast

# Function to find peak kW for given day
def Peak_Demand_Forecast(Demand_Data, hour, days):
    # Initial peak demand
    Peak_Demand = 0
    # check for last day of year to loop load data to beginning of year
    if hour == len(Demand_Data) - 25:
        hour = 0
    # Find peak demand
    for row in Demand_Data[(hour+(days*24+1)):(hour+((days+1)*24+1))]:
        if float(row[4]) > Peak_Demand:
            Peak_Demand = float(row[4])

    return Peak_Demand

# Function to charge BESS
def Charge(PV_Data, BESS_Dispatch, State_of_Charge, Hour, Discharge_Charge):
    # Temporary index variable
    index_temp = Hour + Year*len(PV_Data)
    if Hour == len(PV_Data) - 24:
        Hour = 0
    for row in PV_Data[Hour:Hour+24]:
        # Charging BESS off PV
        BESS_Dispatch[index_temp][4] = float(row[4])*One_Way_Eff
        Discharge_Charge.append([0,float(row[4])])
        index_temp = index_temp + 1
    return BESS_Dispatch

# Function to charge and discharge BESS
def Charge_Discharge(PV_Data, Demand_Data, BESS_Dispatch, State_of_Charge, Excess_Threshold, Hour, Discharge_Charge):
    # Temporary index variables.  PV data requires different index since it loops back to beginning of list
    # Whereas the BESS dispatch list grows until the program stops
    index_temp = Hour + Year*len(PV_Data)
    if Hour == len(PV_Data) - 24:
        Hour = 0
    index_temp_PV = Hour
    for row in Demand_Data[Hour:Hour+24]:
        # Discharge if peak detected
        if float(row[4]) >= Excess_Threshold:
            BESS_Dispatch[index_temp][4] = -1*(float(row[4]) - Excess_Threshold) + float(PV_Data[index_temp_PV][4])*One_Way_Eff
            Discharge_Charge.append([float(row[4]) - Excess_Threshold, float(PV_Data[index_temp_PV][4])])
        # Otherwise charge
        else:
            BESS_Dispatch[index_temp][4] = float(PV_Data[index_temp_PV][4])*One_Way_Eff
            Discharge_Charge.append([0, float(PV_Data[index_temp_PV][4])])
        index_temp = index_temp + 1
        index_temp_PV = index_temp_PV + 1
    return BESS_Dispatch

# Function to integrate discrete data in one hour increments
def integrate(Point_One, Point_Two, threshold):
    # Shift curve down by threshold
    Point_One = Point_One - threshold
    Point_Two = Point_Two - threshold
    # If dispatch curve crosses x-axis, locate point of intersection and area under curve = sum of area under two triangles
    if (Point_One > 0 and Point_Two < 0) or (Point_One < 0 and Point_Two > 0):
        distance = math.sqrt((1) ** 2 + (Point_Two - Point_One) ** 2)  # distance between two points on dispatch curve
        theta = math.asin(1 / distance)  # Angle between curve from hour one to hour two and vertical line @ hour one
        intersection = abs(Point_One) * math.tan(theta)  # Intersection point on the x-axis
        if threshold > 0 and Point_Two < 0:
        # If integrate being used to calculate the peak kWh, we are not interested in the kWh below the threshold, so ignore that triangle
            kWh_Charge = (0.5) * (intersection) * (Point_One)
        elif threshold > 0 and Point_One < 0:
            kWh_Charge = (0.5) * (1 - intersection) * (Point_Two)
        else:
        # Other wise calculate the net area of the two triangles
            kWh_Charge = (0.5) * (intersection) * (Point_One) + (0.5) * (1 - intersection) * (Point_Two)  # Area under the curve
    # If dispatch curve doesn't cross x-axis, then area under curve = area under trapezoid
    else:
        kWh_Charge = (1 / 2) * (Point_One + Point_Two)
    return kWh_Charge

# Function to update BESS SOC
def Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour, PV_Data, Load_Data, Discharge_Charge):
    # Temporary index variable
    kWh_Charge = 0
    index_temp = Hour + Year*len(PV_Data)
    index_temp_PV = Hour
    for row in BESS_Dispatch[index_temp:index_temp+24]:
        index_temp +=  1
        index_temp_PV += 1
        # Get kW charge for current and next hour
        Hour_One_Power = float(row[4])
        if index_temp >= len(BESS_Dispatch):
            Hour_Two_Power = 0
        else:
            Hour_Two_Power = float(BESS_Dispatch[index_temp][4])

        # If discharging, included one way efficiency to get correct value that the BESS must dispatch
        # e.g. if the BESS much dispatch 80kW with 80% one way efficiency, then it must actually discharge
        # 80kW/.8 = 100kW to make sure the losses are accounted for
        # Efficiency already considering for the input power from PV
        if Hour_One_Power < 0:
            Hour_One_Power /= One_Way_Eff
        if Hour_Two_Power < 0:
            Hour_Two_Power /= One_Way_Eff

        # Calculate area under this curve
        kWh_Charge = integrate(Hour_One_Power, Hour_Two_Power, 0)

        # Update SOC
        State_of_Charge = State_of_Charge + kWh_Charge/BESS_Capacity
        # Correct dispatch when system either overcharges
        if State_of_Charge > 1.0 and kWh_Charge > 0:
            Delta_SOC = State_of_Charge - 1.0                               # Calculate % the SOC overcharges
            State_of_Charge = State_of_Charge - kWh_Charge / BESS_Capacity  # revert SOC update
            Hour_Two_Power = 0                                              # Fix the dispatch at hour two to be zero
            kWh_Charge_new = integrate(Hour_One_Power, Hour_Two_Power, 0)   # Calculate resulting kWh
            # If this change is sufficient to prevent overcharging
            if ((kWh_Charge+0.05)-kWh_Charge_new) >= Delta_SOC*BESS_Capacity and index_temp < len(Discharge_Charge):
                BESS_Dispatch[index_temp][4] = Hour_Two_Power               # Only altertion to dispatch is to fix hour two to zero
                Discharge_Charge[index_temp][1] = Hour_Two_Power
            # If this is not sufficient, hour one must be changed as well.
            # I do not let the program put hour two below zero because it will enter an oscillatory charge - discharge cycle
            else:
                kWh_Charge_new = kWh_Charge - (Delta_SOC * BESS_Capacity)   # Calculate the need kWh to not exceed 1.0 SOC
                Updated_Dispatch = 2 * kWh_Charge_new                       # Calculate corresponding hour one power w/ hour two = 0
                Updated_Charge = Hour_One_Power - Updated_Dispatch          # Calculate diff. between original hour one power and new hour one power
                Hour_One_Power = Updated_Dispatch                           # Update hour one power
                if index_temp < len(Discharge_Charge):                         # Check for end of data
                    BESS_Dispatch[index_temp][4] = Hour_Two_Power           # Change dispatch @ hour two to zero
                    # Discharge_Charge[index_temp][0] = 0
                    Discharge_Charge[index_temp][1] = 0
                    # If the BESS is peak shaving while charging, change the dispatch to reduce the amount charged while
                    # not changing the dispatched power so peak shaving maintained
                    if float(Load_Data[index_temp_PV-1][4]) >= Excess_Threshold:
                        BESS_Dispatch[index_temp-1][4] = -1 * (float(Load_Data[index_temp_PV-1][4]) - Excess_Threshold) + float(PV_Data[index_temp_PV-1][4]) * One_Way_Eff - Updated_Charge
                    # Otherwise just reduce the amount being charge
                    else:
                        BESS_Dispatch[index_temp-1][4] = float(PV_Data[index_temp_PV-1][4]) * One_Way_Eff - Updated_Charge
                Discharge_Charge[index_temp-1][1] = float(PV_Data[index_temp_PV - 1][4]) - Updated_Charge
                kWh_Charge_new = integrate(Hour_One_Power, Hour_Two_Power, 0)   # Calculate new kWh in
            State_of_Charge = State_of_Charge + kWh_Charge_new / BESS_Capacity  # Update SOC

        # Correct dispatch when system over discharges
        if State_of_Charge < (1-MDOD) and kWh_Charge < 0:
            Delta_SOC = (1-MDOD) - State_of_Charge                              # Calculate % that the SOC is exceeded
            State_of_Charge = State_of_Charge - kWh_Charge / BESS_Capacity      # revert SOC update
            kWh_Charge_new = kWh_Charge + (Delta_SOC*BESS_Capacity)             # Calculate correct kWh to reach max charge
            Updated_Dispatch = 2 * kWh_Charge_new - Hour_One_Power              # Calculate new dispatch via area of trapezoid
            State_of_Charge = State_of_Charge + kWh_Charge_new / BESS_Capacity  # correct SOC update
            if index_temp < len(Discharge_Charge):
                # Allow updated dispatch assuming the PV output is sufficient to charge
                if float(PV_Data[index_temp_PV][4]) > Updated_Dispatch:
                    BESS_Dispatch[index_temp][4] = Updated_Dispatch
                    Discharge_Charge[index_temp][1] += Updated_Dispatch - (Hour_One_Power - Discharge_Charge[index_temp][0])
                else:
                # Otherwise set the dispatch to be zero and recalculate the kWh charge with new dispatch
                # Can't avoid discharging below the MDOD in this situation
                    BESS_Dispatch[index_temp][4] = 0
                    Hour_Two_Power = BESS_Dispatch[index_temp][4]
                    kWh_Charge = (0.5)*(Hour_One_Power+Hour_Two_Power)
                    State_of_Charge = State_of_Charge + kWh_Charge/BESS_Capacity
                    Discharge_Charge[index_temp][0] = 0
                    Discharge_Charge[index_temp][1] = 0
        # Update time-series SOC data
        if index_temp < len(BESS_Dispatch):
            State_of_Charge_Monitor[index_temp][4] = State_of_Charge
    return State_of_Charge

# -------------------------------------------------------------------- #

# ---------------------- Dispatch Algorithm -------------------------- #
# Initialize variables
Hour = 0                                         # Hour is on zero base
Day = 1                                          # Day is on one base
Year = 0                                         # Year is on zero base
Clear_List = copy.deepcopy(PV_Data)              # Create list of lists in same format as PV data but with no power data
for row in Clear_List:
    row[4] = 0
BESS_Dispatch = copy.deepcopy(Clear_List)         # deep copy the cleared list so the dispatch and SOC list of lists have the same format
State_of_Charge_Monitor = copy.deepcopy(Clear_List)
Net_POI_Load = copy.deepcopy(Clear_List)
Net_System_Load = copy.deepcopy(Load_Data)
Discharge_Charge = []
State_of_Charge_Monitor[0][4] = State_of_Charge  # Initial SOC
dispatching = True                               # start dispatching
Excess_Threshold_Original = Excess_Threshold     # Variable to store the initially specific excess demand threshold
BESS_Capacity_Original = BESS_Capacity           # Store the initially specified BESS capacity
Annual_kWh_Shaved = []
# Begin hourly dispatch
while dispatching:

    # Loop data at end of year
    if Hour == len(PV_Data) - 1:
        Discharge_Charge.append([0,0]) # Append row to end of this list to keep same length as other lists
        # Calculate net load at the POI
        temp_index_Load = 0
        temp_index = len(PV_Data)*Year
        for row in PV_Data:
            if float(BESS_Dispatch[temp_index][4]) != 0 and float(row[4]) > 0:
                Net_POI_Load[temp_index][4] = float(row[4]) - float(BESS_Dispatch[temp_index][4]) - float(row[4])*(1-One_Way_Eff)
            else:
                Net_POI_Load[temp_index][4] = float(row[4]) - float(BESS_Dispatch[temp_index][4])
            Net_System_Load[temp_index][4] = float(Load_Data[temp_index_Load][4])-float(Net_POI_Load[temp_index][4])
            temp_index += 1
            temp_index_Load += 1
        # Calculate kWh shaved this year
        temp_index = len(PV_Data)*Year
        kWh_Shaved = 0
        for row in PV_Data:
            #Hour_One_Power = float(Net_POI_Load[temp_index][4])
            #             #if temp_index == len(Net_POI_Load)-1:
            #             #    Hour_Two_Power = 0
            #             #else:
            #             #    Hour_Two_Power = int(Net_POI_Load[temp_index+1][4])
            Hour_One_Power = float(Discharge_Charge[temp_index][0])
            if temp_index == len(Discharge_Charge) - 1:
                Hour_Two_Power = 0
            else:
                Hour_Two_Power = float(Discharge_Charge[temp_index+1][0])
            kWh_Shaved += integrate(Hour_One_Power, Hour_Two_Power, 0)
            temp_index += 1
        Annual_kWh_Shaved.append(kWh_Shaved/1000)
        # Increment year and cancel dispatching if simulation duration reached
        Year = Year + 1
        if Year == Simulation_Duration:
            Peak_load = 0
            for row in Load_Data:
                if Peak_load < int(row[4]):
                    Peak_load = int(row[4])
            dispatching = False
            break
        # Extend BESS Dispatch and SOC monitor lists additional year
        index = len(PV_Data)*Year
        for row in Clear_List:
            BESS_Dispatch.append(copy.copy(row))
            State_of_Charge_Monitor.append(copy.copy(row))
            Net_POI_Load.append(copy.copy(row))
            Net_System_Load.append(copy.copy(row))
            BESS_Dispatch[index][0] = int(row[0]) + Year
            State_of_Charge_Monitor[index][0] = int(row[0]) + Year
            Net_POI_Load[index][0] = int(row[0]) + Year
            Net_System_Load[index][0] = int(row[0]) + Year
            index = index + 1
        # Degrade BESS capacity and grow load
        BESS_Capacity = BESS_Capacity*(1 - BESS_Degredation)
        if BESS_Capacity < BESS_Capacity_Original*Warranty_Gaurantee:
            BESS_Capacity = BESS_Capacity_Original*Warranty_Gaurantee
        if Year == BESS_Capacity_Increase_Freq:
            BESS_Capacity += BESS_Capacity_Increase
            BESS_Capacity_Increase_Freq += BESS_Capacity_Increase_Freq
        for row in Load_Data:
            row[4] = int(row[4])*(1 + Load_Growth)
        # Reset hour and day for new year and re-initialize SOC
        State_of_Charge_Monitor[Year*len(PV_Data)][4] = State_of_Charge
        Hour = 0
        Day = 1
        Forecast_Accuracy_Factor += Forecast_Accuracy_Factor_Annual_Growth

    # Load and PV forecasting
    # Reset excess demand threshold
    Excess_Threshold = Excess_Threshold_Original
    # Get peak load and PV output forecasts for current hour to current hour + 24
    Peak_Load_kWh_Today = Energy_Forecast(Load_Data, Hour, Excess_Threshold, 0)
    PV_kWh_Today = Energy_Forecast(PV_Data, Hour, 0, 0)
    Peak_kW_Today = Peak_Demand_Forecast(Load_Data, Hour, 0)
    # Calculate Net Peak Load Today
    Net_Peak_kWh_Today = Peak_Load_kWh_Today - PV_kWh_Today

    # Get peak load and PV output forecasts for current hour + 24  to current hour + 48
    Peak_Load_kWh_Tom = Energy_Forecast(Load_Data, Hour, Excess_Threshold, 1)
    PV_kWh_Tom = Energy_Forecast(PV_Data, Hour, 0, 1)
    Peak_kW_Tom = Peak_Demand_Forecast(Load_Data, Hour, 1)
    # Calculate net peak load tomorrow
    Net_Peak_kWh_Tom = Peak_Load_kWh_Tom - PV_kWh_Tom

    # Determine Current charge status of BESS
    Current_Available_Capacity = (State_of_Charge - (1 - MDOD)) * BESS_Capacity

    if Peak_kW_Today <= Excess_Threshold and Peak_kW_Tom <= Excess_Threshold and State_of_Charge < 0.98:
        # If there are no peaks for the next two days.  Just charge.  The SOC update functions will handle where the
        # SOC is already max and will update the dispatch accordingly
        BESS_Dispatch = Charge(PV_Data, BESS_Dispatch, State_of_Charge, Hour, Discharge_Charge)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour, PV_Data, Load_Data, Discharge_Charge)
    elif Peak_kW_Today <= Excess_Threshold and Peak_kW_Tom >= Excess_Threshold and State_of_Charge < 0.98:
        # If there is a peak detected tomorrow and no peak today, run the charging function to prepare for tomorrow
        BESS_Dispatch = Charge(PV_Data, BESS_Dispatch, State_of_Charge, Hour, Discharge_Charge)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour, PV_Data, Load_Data, Discharge_Charge)
    elif Peak_kW_Today >= Excess_Threshold and Peak_kW_Tom <= Excess_Threshold:
        # If there is a peak today and no peak tomorrow, discharge freely today with no need to prep for tomorrow
        BESS_Dispatch = Charge_Discharge(PV_Data, Load_Data, BESS_Dispatch, State_of_Charge, Excess_Threshold, Hour, Discharge_Charge)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour, PV_Data, Load_Data, Discharge_Charge)
    else:
        # If there is a peak both days, determine how much to shave today while prepping for tomorrow
        # If Net_Peak_kWh_Tom < 0 that indicates that the BESS is charging more than discharging
        # and we don't want the algorithm to believe it will have access to that energy today, so disregard it
        if Net_Peak_kWh_Tom < 0:
            Net_Peak_kWh_Tom = 0
        while Current_Available_Capacity*One_Way_Eff < (Net_Peak_kWh_Today + Net_Peak_kWh_Tom)*Forecast_Accuracy_Factor:
            # Update threshold
            Excess_Threshold = Excess_Threshold + 100
            # Reforecast peak kWh
            Peak_Load_kWh_Today = Energy_Forecast(Load_Data, Hour, Excess_Threshold, 0)/One_Way_Eff
            Peak_Load_kWh_Tom = Energy_Forecast(Load_Data, Hour, Excess_Threshold, 1)/One_Way_Eff
            # Recalculate net kWh
            Net_Peak_kWh_Today = Peak_Load_kWh_Today - PV_kWh_Today*One_Way_Eff
            Net_Peak_kWh_Tom = Peak_Load_kWh_Tom - PV_kWh_Tom*One_Way_Eff
            # If Net_Peak_kWh_Tom < 0 that indicates that the BESS is charging more than discharging
            # and we don't want the algorith to believe it will have access to that energy today, so disregard it
            if Net_Peak_kWh_Tom < 0:
                Net_Peak_kWh_Tom = 0
        # Once threshold updated, shave peaks
        BESS_Dispatch = Charge_Discharge(PV_Data, Load_Data, BESS_Dispatch, State_of_Charge, Excess_Threshold, Hour, Discharge_Charge)
        State_of_Charge = Update_SOC(BESS_Dispatch, State_of_Charge, State_of_Charge_Monitor, BESS_Capacity, Hour, PV_Data, Load_Data, Discharge_Charge)

    # Increment time
    Day = Day + 1
    Hour = Hour + 24

# ------------------------------------------------------------------- #

# ---------------------------- Output ------------------------------- #
# Build list of demand charge for each month
Monthly_Demand_Charges = [[0,0,0,1.0,0]]
Year_Actual = int(Net_System_Load[0][0])
Month = int(Net_System_Load[0][1])
index = 0
month_index = 0
load_index = 0
Year = 0
# Begin looping through full set of substation load data to gather desired statistics
# *** The list of lists which holds this data is called Month_Demand_Charges, the final csv output is called 'Monthly Statistics'
while Year_Actual == int(Net_System_Load[index][0]) and Year < Simulation_Duration:
    # Loop through each month
    while Month == int(Net_System_Load[index][1]):
        # Calculate Losses for charging and discharging
        Hour_One_Losses = (Discharge_Charge[index][0]/One_Way_Eff - Discharge_Charge[index][0]) + (Discharge_Charge[index][1] - Discharge_Charge[index][1]*One_Way_Eff)
        # Check for end of PV data
        if load_index == (len(Load_Data)-1):
            load_index = 0
        # Calculate last point and break
        if index == len(Net_System_Load)-1:
            Hour_Two_Losses = 0
            Monthly_Demand_Charges[month_index][4] += integrate(Hour_One_Losses, Hour_Two_Losses, 0)
            break
        Hour_Two_Losses = (Discharge_Charge[index+1][0] / One_Way_Eff - Discharge_Charge[index][0]) + (Discharge_Charge[index+1][1] - Discharge_Charge[index][1] * One_Way_Eff)
        # Integrate the hourly power losses (in W) to get energy loss (in Wh)
        Monthly_Demand_Charges[month_index][4] += integrate(Hour_One_Losses, Hour_Two_Losses, 0)
        if Monthly_Demand_Charges[month_index][3] > float(State_of_Charge_Monitor[index][4]):
            # Find lowest SOC each month
            Monthly_Demand_Charges[month_index][3] = float(State_of_Charge_Monitor[index][4])
        if float(BESS_Dispatch[index][4]) != 0:
            # Track monthly BESS operating hours
            Monthly_Demand_Charges[month_index][2] += 1
        if Monthly_Demand_Charges[month_index][0] < (float(Net_System_Load[index][4]) - Excess_Threshold_Original):
            # Update Demand charge is demand threshold exceeded and value is larger than the last found for this month
            Monthly_Demand_Charges[month_index][0] = float(Net_System_Load[index][4] - Excess_Threshold_Original)
        if Monthly_Demand_Charges[month_index][1] < float(Load_Data[load_index][4])/((1+Load_Growth)**(Simulation_Duration-(Year+1))) - Excess_Threshold_Original:
            # Update demand charge for system w/o BESS
            Monthly_Demand_Charges[month_index][1] = float(Load_Data[load_index][4])/((1+Load_Growth)**(Simulation_Duration-(Year+1))) - Excess_Threshold_Original
        index += 1
        load_index += 1
    # Again just break when the end of the data is found (for simplicity)
    if index == len(Net_System_Load)-1:
        break
    # Update month and index used for month
    Month = int(Net_System_Load[index][1])
    month_index += 1
    Operating_Hours = 0
    # Update year after 12 months
    if len(Monthly_Demand_Charges) == 12*(Year+1):
        load_index = 0
        Month = 1
        Year += 1
        Year_Actual = int(Net_System_Load[index][0])
    # Add extra item to list
    Monthly_Demand_Charges.append([0,0,0,1.0,0])

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

Net_Sys_Load = open('Net_System_Load.csv', 'w')
Net_Sys_Load_Writer = csv.writer(Net_Sys_Load)
for row in Net_System_Load:
    Net_Sys_Load_Writer.writerow(row)
Net_Sys_Load.close()

# Create .csv in correct format for OpenDSS and in standard format as well
Net_POI_Load_OpenDSS = []
index = 0
for row in Net_POI_Load:
    Net_POI_Load_OpenDSS.append(int(row[4])/Sbase)
    index += 1
Net_POI_Load_OpenDSS_File = open('Net_POI_Load_OpenDSS.csv', 'w')
Net_POI_Load_OpenDSS_Writer = csv.writer(Net_POI_Load_OpenDSS_File)
Net_POI_Load_File = open('Net_POI_Load.csv', 'w')
Net_POI_Load_Writer = csv.writer(Net_POI_Load_File)
for item in Net_POI_Load_OpenDSS:
    Net_POI_Load_OpenDSS_Writer.writerow([item])
for row in Net_POI_Load:
    Net_POI_Load_Writer.writerow(row)
Net_POI_Load_OpenDSS_File.close()
Net_POI_Load_File.close()

# Create .csv file with monthly demand charges
Monthly_Demand_Charges_Headers = ['Demand Charge w/ BESS (kW)', 'Demand Charge w/o BESS (kW)', 'Operating Hours (Hours)', 'Lowest SOC (%)', 'Losses (kWh)']
Monthly_Demand_Charges.insert(0, Monthly_Demand_Charges_Headers)
Monthly_Demand_Charges_File = open('Monthly_Statistics.csv', 'w')
Monthly_Demand_Charges_Writer = csv.writer(Monthly_Demand_Charges_File)
Monthly_Demand_Charges_Writer.writerow(Monthly_Demand_Charges[0])
for row in Monthly_Demand_Charges[1:]:
    # divide by 1000 to convert W and Wh to kW and kWh
    row[0] = row[0] / 1000
    row[1] = row[1] / 1000
    row[3] = row[3] * 100
    row[4] = row[4] / 1000
    Monthly_Demand_Charges_Writer.writerow(row)
Monthly_Demand_Charges_File.close()

# Create.csv file with annual kWh shaved
Annual_kWh_Shaved_Header = 'Annual Energy Shaved (kWh)'
Annual_kWh_Shaved.insert(0, Annual_kWh_Shaved_Header)
Annual_kWh_Shaved_File = open('Annual_kWh_Shaved.csv', 'w')
Annual_kWh_Shaved_Writer = csv.writer(Annual_kWh_Shaved_File)
Annual_kWh_Shaved_Writer.writerow([Annual_kWh_Shaved[0]])
for item in Annual_kWh_Shaved[1:]:
    Annual_kWh_Shaved_Writer.writerow([item])
Annual_kWh_Shaved_File.close()
# ------------------------------------------------------------------- #



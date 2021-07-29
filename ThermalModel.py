import ReadSheet as read
import matplotlib.pyplot as plt
import numpy as np
import pybamm

################################ Constants ####################################
rho = 1.225 # kg/m^3 ; Density of air
c_v = 0.718 # kJ/kg.K ; Specific heat with constant volume at 300K
temp_set = 75 # degrees F ; Baseline temp
h = 10 # W/m^2.K ; Convection heat transfer coefficient
c_p = .7585 # kJ/kg.K ; Specific heat at constant pressure (atmospheric)
          # Average of steel and air; Steel = 0.51, Air = 1.007
###############################################################################


################################ Functions ####################################
# Converts Fahrenheit to Kelvin
def f_to_k(f):
    
    k = ((f - 32) / 1.8) + 273.15
    
    return(k)

# Converts Kelvin to Fahrenheit
def k_to_f(k):
    
    f = 1.8 * (k - 273.15) + 32
    
    return(f)

# Converts British Thermal Units (BTU) to kiloJoules (kJ)
def BTU_to_kJ(BTU):
    
    kJ = BTU * 1055.056 / 1000
    
    return(kJ)


# Calculates the change in daily temperature per hour
def max_min_temp_diff(clim, month):
    
    max_temp = f_to_k(read.find_num(clim, month, 'MLY-TMAX-NORMAL'))
    min_temp = f_to_k(read.find_num(clim, month, 'MLY-TMIN-NORMAL'))
    avg_temp = max_temp - min_temp # K
    
    return(avg_temp)


# Calculates the difference in temperature between months
def monthly_temp_diff(clim, month, name):
    
    if month =='12':
        monthnext = '1'
    else:
        monthnext = str(int(month)+1)
        
    max_temp_1 = f_to_k(read.find_num(clim, month, name)) # K
    max_temp_2 = f_to_k(read.find_num(clim, monthnext, name)) # K
    monthly_max_diff = max_temp_2 - max_temp_1 # K
    
    return(monthly_max_diff)


# Calculates the hourly temperature
# Inputs:
    # min_temp: The daily minimum temperature
    # max_temp: The daily maximum temperature
    # avg: The temperature between monthly max and min temperature
    # month: The month we're currently in (format: 1, 2, 3, etc.)
# Outputs:
    # hrly: The estimated temperature at each hour
def daily_temps(min_temp, max_temp, avg, month):
    
    hrly = []
    
    day_start = 0 # When day starts; 12am
    low_time = 6 # Point where temps start increasing; ~6am
    high_time = 15 # Point where temps start falling; ~2-3pm
    day_end = 24 # Day ends, cycle repeats; 12am
    
    for i in range(day_start+1,day_end+1):
        
        start_temp = (max_temp - avg[month]/((day_end-high_time)+low_time) * (day_end-high_time))
        
        if i < low_time:
            temp = start_temp - avg[month]/((day_end-high_time)+low_time) * i
            if temp < min_temp:
                hrly.append(min_temp)
            else:
                hrly.append(temp)
                
        elif low_time <= i and i < high_time:
            temp = (min_temp + avg[month]/(high_time-low_time) * (i-low_time))
            if temp > max_temp:
                hrly.append(max_temp)
            else:
                hrly.append(temp)
                
        else:
            temp = max_temp - avg[month]/((day_end-high_time)+low_time) * (i-high_time)
            hrly.append(temp)
        
    return(hrly)


# Calculates the changes in monthly temperature
# Inputs:
    # region: Which location in the US to look at
    # start: The hour of the year to start at (Min = 0, Max = 8759)
    # end: The hour of the year to end at (Min = 1, Max = 8760)
# Outputs:
    # mnly: The estimated temperature at each hour for the specified hours
def monthly_temp(region, start, end):
    
    # Read climate data
    climate = read.create_dataframes(read.define_sheet_data('Climate Data'), 'month')
    
    # Initializing lists
    avg = []
    minim = []
    maxim = []
    mnly = []
    
    # Determines changes between monthly max and mins
    for i in climate[region].index:
        avg.append(max_min_temp_diff(climate[region], i))
        maxim.append(monthly_temp_diff(climate[region], i, 'MLY-TMAX-NORMAL'))
        minim.append(monthly_temp_diff(climate[region], i, 'MLY-TMIN-NORMAL'))
    
    # Initializing constants for following loop
    months = 1
    
    time = np.arange(start, end, 1) # Creates the specified range
    
    # Used to calculate the temperature change per hour
    for j in time:

        # For monthly changes
        if j % 730 == 0 or j == start:
            if j == start:
                months = int(np.floor(j/730)) + 1
            else:
                if months < 12:
                    months += 1
                if months == 12:
                    months = 12

        mon_max_chg = maxim[months-1]/(365/12) * ((j/24)%(365/12))
        mon_min_chg = minim[months-1]/(365/12) * ((j/24)%(365/12))
        
        # For daily changes
        if (j % 24 == 0 and j != 0) or j == end-1:
            
            day_min = f_to_k(read.find_num(climate[region], str(months), 'MLY-TMIN-NORMAL')) + mon_min_chg
            day_max = f_to_k(read.find_num(climate[region], str(months), 'MLY-TMAX-NORMAL')) + mon_max_chg        
            for i in daily_temps(day_min, day_max, avg, months-1):
                mnly.append(i)

        # Looks for the end of the year and resets the date
        if j % 8760 == 0 and j != 0:
            months = 1
    
    return(mnly)


# Determines the heat generated by convection
# Inputs:
    # mnly: Total temperature data
    # housing: Housing pandas dataframe
    # temp_set: Set interior temperature
    # h: See constant on line 10
    # step: Hours between recorded temperatures
# Returns: 
# Next steps: 
def Q_convection(mnly, housing, temp_set, h, step):
    #Inputs: h, temp_set, surface_area (of five walls (not bottom)), hourly_temp
    
    Q_ambient = []
    
    # Caluclate total surface area using width/height/depth
    width = read.find_num(housing, housing.index[1], 'Width (mm)') / 1000 # m
    height = read.find_num(housing, housing.index[1], 'Height (mm)') / 1000 # m
    depth = read.find_num(housing, housing.index[1], 'Depth (mm)') / 1000 # m

    s_area = 2 * depth * height + 2 * height * width + 2 * depth * width
    s_used = s_area - depth * width
    
    m = (read.find_num(housing, housing.index[1], 'Weight (kg)') / s_area) * s_used
    
    for i in range(0,len(mnly),step):
        Q_ambient.append(h * s_area * (-mnly[i] + temp_set))
        
    
    return(Q_ambient, m)

# Determines heat contribution to storage unit based off battery conditions
# Pull thermal data from pybamm (set in terms of kJ)
# Inputs:
    # cell: Cell dataframe
    # temp_set: Set interior temperature
def Q_bat(temp_set):
    
    components = read.create_dataframes(read.define_sheet_data('Battery_System_Components'), "Select a Configuration")
    cell = components[0]
    module = components[1]
    rack = components[2]
    housing = components[3]
    
    
    options = {"thermal": 'x-full'}
    #chemistry = pybamm.parameter_sets.Chen2020 #this was already here
    #parameter_values = pybamm.ParameterValues(chemistry=chemistry) # this was already here
    model = pybamm.lithium_ion.SPMe(options=options)
    parameter_values = model.default_parameter_values
    
    experiment = pybamm.Experiment(
        [
            ('Discharge at 4C for 10 hours or until 3.3 V',
             'Rest for 1 hour',
             'Charge at 1 A until 4.1 V',
             'Hold at 4.1 V until 50 mA',
             'Rest for 1 hour'),
        ] * 3
    )
    
    parameter_values['Ambient temperature [K]'] = temp_set
    parameter_values['Negative current collector thickness [m]'] = read.find_num(cell, cell.index[1], 'Thickness [m]')
    parameter_values['Positive current collector thickness [m]'] = read.find_num(cell, cell.index[0], 'Thickness [m]')
    parameter_values['Negative electrode active material volume fraction'] = .75
    parameter_values['Negative electrode porosity'] = .25
    parameter_values['Negative electrode thickness [m]'] = read.find_num(cell, cell.index[2], 'Thickness [m]')
    #parameter_values['Positive Electrode Chemistry (NCA/NMC with ratio, LFP)'] # No defaut value in pybamm
    parameter_values['Positive electrode active material volume fraction'] = .665
    parameter_values['Positive electrode porosity'] = .335
    parameter_values['Positive electrode thickness [m]'] = read.find_num(cell, cell.index[5], 'Thickness [m]')
    parameter_values['Separator porosity'] = read.find_num(cell, cell.index[12], 'Porosity (%)')
    parameter_values['Separator thickness [m]'] = read.find_num(cell, cell.index[12], 'Thickness [m]')
    
    
    sim = pybamm.Simulation(model, parameter_values=parameter_values, experiment = experiment)
    sim.solve()
    bam_data = sim.solution['Total heating [W.m-3]'].entries
    
    
    heat_range = []
    for i in range(0,len(bam_data[0,:])):
        heat_range.append(sum(bam_data[:,i]))
    
    
    cells = read.find_num(module, module.index[2], 'Number per module')
    modules = read.find_num(rack, rack.index[0], 'Number per rack')
    racks = read.find_num(housing, housing.index[0], 'Number')
    
    bat_thick = read.find_num(cell, cell.index[2], 'Thickness [m]') * 2 + .000025
    bat_width = read.find_num(cell, cell.index[2], 'Width [mm]')
    bat_len = read.find_num(cell, cell.index[2], 'Length [mm]')
    
    # kJ = ((W/m^3 / unitless) * m * m * m) / (J/kJ)
    Q_BAT = (float(sum(heat_range))/float(len(heat_range))) * bat_thick * bat_width * (10**(-3)) * bat_len * (10**(-3)) * ((cells * modules * racks)**2) / 1000
    

    return(Q_BAT)


def Q_hvac(housing, name):
    
    Q_HVAC = BTU_to_kJ(read.find_num(housing, housing.index[2], name)) # kJ
    
    return(Q_HVAC)


    # Calculates the total temperature inside housing
    # Inputs:
        # data: The estimated temperature data
        # h: See constant on line 10
        # step: Hours between temperatures
        # temp_set: Set interior temperature
def total_thermal(temp_data, h, step, temp_set, num_HVAC, T_prev):
    
    # Final equation: (Q_convection + Q_bat - Q_HVAC) / (m*c_p) + T_start = T_final
    # Update such that T_final becomes T_start after first iteration
    # T_start should be the ambient temperature at the starting time for first 
    
    components = read.create_dataframes(read.define_sheet_data('Battery_System_Components'), "Select a Configuration")
    housing = components[3]
        
        
    T_final = []
    T_new = temp_data[0]
    T_start = temp_data[0]
    
    Q_HVAC = Q_hvac(housing, 'BTU Rating (cooling)')
    Q_CON = Q_convection(temp_data, housing, temp_set, h, step)[0]
    Q_BAT = Q_bat(temp_set) # Still working to convert heat to kJ
    
    m = Q_convection(temp_data, housing, temp_set, h, step)[1]
    
    
    for i in range(0,len(Q_CON)):
        #if 0 <= T_start <= 335:
        T_final.append(T_start)
        if T_start > temp_set:
            T_start = ((Q_CON[i] + Q_BAT - Q_HVAC * num_HVAC) / (m * c_p)) + T_new
            T_new = T_start
            # K = ((kJ + kJ - kJ) / (kg * kJ/kg.K)) + K
            '''
        elif T_start < f_to_k(10):
            T_start = ((Q_CON[i] + Q_BAT + Q_HVAC * num_HVAC) / (m * c_p)) + T_new
            T_new = T_start
            '''
        else:
            T_start = ((Q_CON[i] + Q_BAT - Q_HVAC * num_HVAC * .5) / (m * c_p)) + T_new
            T_new = T_start
                
        '''        
        else:
            T_final.append(T_start)
            T_start = ((Q_CON[i] + Q_BAT - Q_HVAC * num_HVAC) / (m * c_p)) + T_new
            T_new = T_start
            c = 1
         '''   
        
        
    if f_to_k((k_to_f(temp_set)-10)) <= sum(T_final)/len(T_final) and sum(T_final)/len(T_final) <= f_to_k((k_to_f(temp_set)+10)):
        print(f"HVAC is sufficiently good with {num_HVAC} HVAC unit(s)!")
        print(f"Average Internal Temperature: {sum(T_final)/len(T_final)} K")
    elif sum(T_final)/len(T_final) > T_prev:
        print(f"HVAC is sufficiently good with {num_HVAC} HVAC unit(s)!")
        print(f"Average Internal Temperature: < {T_prev} K")
    else:
        print(f"HVAC system is not sufficiently good with {num_HVAC} HVAC unit(s)!")
        num_HVAC += 1
        print(f"Average Internal Temperature: {sum(T_final)/len(T_final)} K")
        T_prev = sum(T_final)/len(T_final)
        T_final = total_thermal(temp_data, h, step, temp_set, num_HVAC, T_prev)

    
    
    return(T_final)

###############################################################################


################################### Main ######################################
if __name__ == '__main__':
    
    components = read.create_dataframes(read.define_sheet_data('Battery_System_Components'), "Select a Configuration")
    cell = components[0]
    module = components[1]
    rack = components[2]
    housing = components[3]
    
    
    # Variable variables
    region = 1 # Currently 0 or 1
    start = 6000 # 0 representing Jan 1st
    end = 6100 # 8760 representing Dec 31st
    step = 1 # Number of hours between recording data points
    
    
    # Determines temperature data from region over time period
    temp_data = monthly_temp(region, start, end)
    
    T_prev = 1000000000
    num_HVAC = read.find_num(housing, housing.index[3], 'Number')
    
    # Determines thermal data (The units are off atm so thing look weird)
    thermal_data = total_thermal(temp_data, h, step, f_to_k(temp_set), num_HVAC, T_prev)
    
    
    '''
    # Use to check output thermal data in degrees F 
    x = []
    for i in thermal_data:
        
        x.append(k_to_f(i))
    '''
    
    '''
    # Plot of the temperature per hour in the housing
    time = np.arange(start,start+len(temp_data),step)
    plt.plot(time, temp_data, linestyle = 'solid')
    '''

    x = sum(thermal_data)/len(thermal_data)
   
    

    # Use first plot format due to automatic updates to title
    time = np.arange(start,start+len(thermal_data),step)
    plt.plot(time, thermal_data, linestyle = 'dotted', color ='blue', label = 'Estimated Interior Temperatures')
    #plt.plot(time,temp_data, color ='green', label = 'Ambient Temperature')
    plt.xlabel("Time (Hour)")
    plt.ylabel("Housing Temp (K)")
    plt.title(f"Housing temp per {step} hour(s) over {int(np.floor((end-start)/730))} month(s)")
    plt.axhline(y=x, label = 'Average Interior Temperature')
    plt.axhline(y=f_to_k(temp_set), linestyle = 'dashed', color='black', label ='Set Interior Temperature')
    plt.legend()
    plt.show()
    

'''
    # Prints graph for temperature change
    time = np.arange(start,start+len(data),1)
    plt.plot(time, data)
    plt.xlabel("Time (Hour)")
    plt.ylabel("Temperature (K)")
    plt.title("Temperature per hour over one year")
    plt.show()
'''

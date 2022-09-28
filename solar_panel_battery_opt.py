import numpy as np 
import matplotlib.pyplot as plt 
import casadi 
from dataclasses import dataclass



@dataclass
class BatterySetup:
    max_battery_charge:float 
    max_battery_disscharge:float 
    max_battery_capacity:float 
    min_battery_capacity:float
    rate_limit:float



def main():

    battery = BatterySetup(4,4,10,2,2) #10-30 KWh
    N = int(24*4)
    dt = 15*60
    t = np.linspace(0,24,N)
    elec_cost = np.ones(N)*0.1
    elec_cost[65:80] = 10
    #elec_cost[0:10] = 10000

    avaliable_solar = np.zeros(N)
    #avaliable_solar[30:60] = 1
    solar_sigma = 2
    solar_mu = 12
    solar_peak = 1
    avaliable_solar = np.exp(-1/2*((solar_mu-t)/solar_sigma)**2)
    avaliable_solar = avaliable_solar * 1/np.max(avaliable_solar)
    avaliable_solar *= solar_peak

    export_price_precentage = 0.7

    #house_consum = np.sin(-t*2*np.pi/24) + 1
    house_consum = np.zeros(N)
    house_consum[6*4:8*4] = 1
    house_consum[16*4:22*4] = 3

    WB,WE,QB = opt_battery_strat(elec_cost,house_consum,avaliable_solar,dt,battery,export_price_precentage)

    plot_res(elec_cost,house_consum,avaliable_solar,dt,battery,WB,WE,QB)


def plot_res(elec_cost,house_consum,avaliable_solar,dt:float,battery:BatterySetup,WB,WE,QB):
    N = len(elec_cost)
    t = np.linspace(0,24,N)

    y_rotation = 80


    plt.figure()
    plt.subplot(3,1,1)
    plt.title("Input data")
    plt.plot(t,elec_cost)
    plt.ylabel("Cost [sek/KWh]",rotation=y_rotation)

    plt.subplot(3,1,2)
    plt.plot(t,house_consum)
    plt.ylabel("House consumtion [W]",rotation=y_rotation)

    plt.subplot(3,1,3)
    plt.plot(t,avaliable_solar)
    plt.ylabel("Avaliable solar power [W]",rotation=y_rotation)

    plt.tight_layout()
    plt.savefig('input_data.png',dpi=400)

    plt.figure()
    plt.subplot(3,1,1)
    plt.title("Optimized control")
    plt.plot(t,QB)
    plt.ylabel("Battery charge [KWh]",rotation=y_rotation)

    plt.subplot(3,1,2)
    plt.plot(t,WB)
    plt.ylabel("Battery supply to house [W]",rotation=y_rotation)

    plt.subplot(3,1,3)
    plt.plot(t,WE)
    plt.ylabel("Power drawn from the net [W]",rotation=y_rotation)
    plt.tight_layout()
    plt.savefig('output_data.png',dpi=400)
    plt.show()


    

def sigmoid(x):
    # 0 for x < 0
    # 1 for x > 0

    return 1/(1 + casadi.exp(-x*20))




def opt_battery_strat(elec_cost,house_consum,avaliable_solar,dt:float,battery:BatterySetup,export_price_precentage):
    """
    elec_cost - vector with elec prices fro 24h (SEK)
    house_consum - vector how much wattage the household consumes during 24h (W)
    avaliable_solar - vector of how mus solar energy avaliable (W)
    dt - how many seconds between sample points in the vecotrs (SEC)
    """

    opti = casadi.Opti()

    N = len(elec_cost)
    WB = []
    QB = []
    WE = []

    # Assuming constant wattage between sample points,
    # dt_watt_h should be the "integrating time" in order to sum up KWh
    dt_watt_h = dt/60/60 * 1/1000 

    cost = 0

    for i in range(N):

        # Battery charge at step i
        qb_i = opti.variable()
        opti.subject_to(qb_i <= battery.max_battery_capacity)
        opti.subject_to(qb_i > battery.min_battery_capacity)

        qb_70_devi = qb_i - 0.7*battery.max_battery_capacity

        abs_70_devi = opti.variable()
        opti.subject_to(qb_70_devi <= abs_70_devi)
        opti.subject_to(qb_70_devi >= -1*abs_70_devi)
        #cost += abs_70_devi*1e-9
        cost += sigmoid(abs_70_devi)*0.1

        

        # Battery dunamic equation
        if i > 0:
            opti.subject_to(qb_i == QB[i-1] - WB[i-1]*dt_watt_h)

        # Battery must end with the same charge as it started with
        if i == N-1:
            opti.subject_to(qb_i == QB[0])
      
        QB.append(qb_i)

        # Charge controller, how much wattage from/to the battery
        wb_i = opti.variable()

        # ctrl limit
        opti.subject_to(wb_i<= battery.max_battery_disscharge)
        opti.subject_to(wb_i >= -1*battery.max_battery_charge)

        # rate limit
        if i > 0:
            opti.subject_to(wb_i <= WB[i-1] + battery.rate_limit)
            opti.subject_to(wb_i >= WB[i-1] - battery.rate_limit)

        WB.append(wb_i)

        if i == N-1:
            opti.subject_to(wb_i == WB[-2])

        # How much current is drawn from the net & cells?
        W_house = house_consum[i]
        W_cells = avaliable_solar[i]

        we_i = W_house - W_cells - wb_i
        WE.append(we_i)

        # Add upp elec cost
        J_consume = sigmoid(we_i)*dt_watt_h*elec_cost[i]*we_i

        J_export = sigmoid(-1*we_i)*dt_watt_h*elec_cost[i]*export_price_precentage*we_i

        cost += J_consume + J_export

    opti.solver('ipopt')
    opti.minimize(cost)

    sol = opti.solve()


    WB_RES = []
    WE_RES = []
    QB_RES = []

    for i in range(N):
        WB_RES.append(sol.value(WB[i]))
        WE_RES.append(sol.value(WE[i]))
        QB_RES.append(sol.value(QB[i]))
        


    return WB_RES,WE_RES,QB_RES



if __name__ == '__main__':
    main()



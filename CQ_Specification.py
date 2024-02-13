from SeeQ import *

AHU_Tsa = CQ(description="Supply Air Temperature in the AHU",
             unit=UNIT.DEG_C,
             implementation=[
                    GraphCQ(0, [BRICK.AHU, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor]),
                    GraphCQ(1, [BRICK.AHU, BRICK.hasPart, BRICK.Fan, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor]),
                    GraphCQ(1, [BRICK.AHU, BRICK.feeds, BRICK.Zone, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor])
                    ]
             )

AHU_Tma = CQ(description="Mixed Air Temperature in the AHU",
             unit=UNIT.DEG_C,
             implementation=[
                    GraphCQ(0, [BRICK.AHU, BRICK.hasPoint, BRICK.Mixed_Air_Temperature_Sensor]),
                    GraphCQ(1, [BRICK.AHU, BRICK.hasPart, BRICK.Mixed_Damper, BRICK.hasPoint, BRICK.Mixed_Air_Temperature_Sensor]),
                    GraphCQ(1, [BRICK.AHU, BRICK.feeds, BRICK.Zone, BRICK.hasPoint, BRICK.Mixed_Air_Temperature_Sensor])
                    ]
             )

Epsilon_t = CQ(description = "Temperature threshold", 
               unit=UNIT.UNITLESS, 
               implementation=[
                   DefaultCQ(2.33)
                   ]
               ) 

DelTsf = CQ(description = "Change in temperature across supply fan", 
            unit=UNIT.DEG_C, 
            implementation=[
                DefaultCQ(1.11)
                ]
            ) 

VAV_Tsa = CQ(description="VAV Supply Air Temperature - if not, approximated through the SAT of the AHU",
             unit=UNIT.DEG_C,
             implementation=[
                    GraphCQ(0, [BRICK.VAV, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor]),
                    GraphCQ(1, [BRICK.VAV, BRICK.isPartOf, BRICK.AHU, BRICK.hasPoint, BRICK.Supply_Air_Temperature_Sensor]),
                    ]
             )


VAV_Tzone = CQ(description="VAV Zone Temperature",
               unit=UNIT.DEG_C,
               implementation=[
                      GraphCQ(0, [BRICK.Zone_Air_Temperature_Sensor])
                      ]
              )

AHU_Tra = CQ(description="Return Air Temperature in the AHU",
             unit=UNIT.DEG_C,
             implementation=[
                    GraphCQ(0, [BRICK.AHU, BRICK.hasPoint, BRICK.Return_Air_Temperature_Sensor, BRICK.feeds, BRICK.Zone]),
                    GraphCQ(0, [BRICK.AHU, BRICK.hasPoint, BRICK.Return_Air_Temperature_Sensor]),
                    ]
             )

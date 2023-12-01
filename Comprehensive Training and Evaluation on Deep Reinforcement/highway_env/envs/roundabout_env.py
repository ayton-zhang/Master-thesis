from typing import Tuple, Dict, Text

from gym.envs.registration import register
import numpy as np

from highway_env import utils
from highway_env.envs.common.abstract import AbstractEnv
from highway_env.road.lane import LineType, StraightLane, CircularLane, SineLane
from highway_env.road.road import Road, RoadNetwork
from highway_env.vehicle.controller import MDPVehicle


class RoundaboutEnv(AbstractEnv):

    @classmethod
    def default_config(cls) -> dict:
        config = super().default_config()
        config.update({
            "observation": {
                "type": "Kinematics",
                "absolute": True,
                "features_range": {"x": [-100, 100], "y": [-100, 100], "vx": [-15, 15], "vy": [-15, 15]},
            },
            "action": {
                "type": "DiscreteMetaAction",
                "target_speeds": [0, 8, 16,24,32]
            },
            "incoming_vehicle_destination": None,
            "collision_reward": -1,
            "high_speed_reward": 0.2,
            "right_lane_reward": 0,
            "lane_change_reward": -0.05,
            "screen_width": 600,
            "screen_height": 600,
            "centering_position": [0.5, 0.6],
            "duration": 11,
            "normalize_reward": True
        })
        return config

    def _reward(self, action: int) -> float:
        rewards = self._rewards(action)
        reward = sum(self.config.get(name, 0) * reward for name, reward in rewards.items())
        if self.config["normalize_reward"]:
            reward = utils.lmap(reward, [self.config["collision_reward"], self.config["high_speed_reward"]], [0, 1])
        reward *= rewards["on_road_reward"]
        return reward

    def _rewards(self, action: int) -> Dict[Text, float]:
        return {
            "collision_reward": self.vehicle.crashed,
            "high_speed_reward":
                 MDPVehicle.get_speed_index(self.vehicle) / (MDPVehicle.DEFAULT_TARGET_SPEEDS.size - 1),
            "lane_change_reward": 0,#action in [0, 2],
            "on_road_reward": self.vehicle.on_road
        }

    def _is_terminated(self) -> bool:
        return self.vehicle.crashed

    def _is_truncated(self) -> bool:
        return self.time >= self.config["duration"]

    def _reset(self) -> None:
        self._make_road()
        self._make_vehicles()

    def _make_road(self) -> None:
        # Circle lanes: (s)outh/(e)ast/(n)orth/(w)est (e)ntry/e(x)it.
        center = [0, 0]  # [m]
        radius = 20  # [m]
        alpha = 24  # [deg]

        net = RoadNetwork()
        radii = [radius, radius+4,radius+8]
        n, c, s = LineType.NONE, LineType.CONTINUOUS, LineType.STRIPED
        line = [[c, s],[n, s],[n, c]]
        for lane in range(3): 
            net.add_lane("se", "ex",
                         CircularLane(center, radii[lane], np.deg2rad(90 - alpha), np.deg2rad(alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("ex", "ee",
                         CircularLane(center, radii[lane], np.deg2rad(alpha), np.deg2rad(-alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("ee", "nx",
                         CircularLane(center, radii[lane], np.deg2rad(-alpha), np.deg2rad(-90 + alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("nx", "ne",
                         CircularLane(center, radii[lane], np.deg2rad(-90 + alpha), np.deg2rad(-90 - alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("ne", "wx",
                         CircularLane(center, radii[lane], np.deg2rad(-90 - alpha), np.deg2rad(-180 + alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("wx", "we",
                         CircularLane(center, radii[lane], np.deg2rad(-180 + alpha), np.deg2rad(-180 - alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("we", "sx",
                         CircularLane(center, radii[lane], np.deg2rad(180 - alpha), np.deg2rad(90 + alpha),
                                      clockwise=False, line_types=line[lane]))
            net.add_lane("sx", "se",
                         CircularLane(center, radii[lane], np.deg2rad(90 + alpha), np.deg2rad(90 - alpha),
                                      clockwise=False, line_types=line[lane]))

        # Access lanes: (r)oad/(s)ine
        access = 170  # [m]
        dev = 85+15  # [m]
        a = 5  # [m]
        delta_st = 0.2*dev  # [m]

        delta_en = dev-delta_st
        w = 2*np.pi/dev
        net.add_lane("ser", "ses", StraightLane([2, access], [2, dev/2], line_types=(s, c)))
        net.add_lane("ses", "se", SineLane([2+a, dev/2], [2+a, dev/2-delta_st], a, w, -np.pi/2, line_types=(c, c)))
        net.add_lane("sx", "sxs", SineLane([-2-a, -dev/2+delta_en], [-2-a, dev/2], a, w, -np.pi/2+w*delta_en, line_types=(c, c)))
        net.add_lane("sxs", "sxr", StraightLane([-2, dev / 2], [-2, access], line_types=(n, c)))
        net.add_lane("sxr", "ser", StraightLane([-2, access],[2, access],line_types=(n,n)))

        net.add_lane("eer", "ees", StraightLane([access, -2], [dev / 2, -2], line_types=(s, c)))
        net.add_lane("ees", "ee", SineLane([dev / 2, -2-a], [dev / 2 - delta_st, -2-a], a, w, -np.pi / 2, line_types=(c, c)))
        net.add_lane("ex", "exs", SineLane([-dev / 2 + delta_en, 2+a], [dev / 2, 2+a], a, w, -np.pi / 2 + w * delta_en, line_types=(c, c)))
        net.add_lane("exs", "exr", StraightLane([dev / 2, 2], [access, 2], line_types=(n, c)))
        net.add_lane("exr", "eer", StraightLane([access,2],[access,-2],line_types=(n,n)))

        net.add_lane("ner", "nes", StraightLane([-2, -access], [-2, -dev / 2], line_types=(s, c)))
        net.add_lane("nes", "ne", SineLane([-2 - a, -dev / 2], [-2 - a, -dev / 2 + delta_st], a, w, -np.pi / 2, line_types=(c, c)))
        net.add_lane("nx", "nxs", SineLane([2 + a, dev / 2 - delta_en], [2 + a, -dev / 2], a, w, -np.pi / 2 + w * delta_en, line_types=(c, c)))
        net.add_lane("nxs", "nxr", StraightLane([2, -dev / 2], [2, -access], line_types=(n, c)))
        net.add_lane("nxr", "ner", StraightLane([2, -access],[-2, -access],line_types=(n,n)))

        net.add_lane("wer", "wes", StraightLane([-access, 2], [-dev / 2, 2], line_types=(s, c)))
        net.add_lane("wes", "we", SineLane([-dev / 2, 2+a], [-dev / 2 + delta_st, 2+a], a, w, -np.pi / 2, line_types=(c, c)))
        net.add_lane("wx", "wxs", SineLane([dev / 2 - delta_en, -2-a], [-dev / 2, -2-a], a, w, -np.pi / 2 + w * delta_en, line_types=(c, c)))
        net.add_lane("wxs", "wxr", StraightLane([-dev / 2, -2], [-access, -2], line_types=(n, c)))
        net.add_lane("wxr", "wer", StraightLane([-access,-2],[-access,2],line_types=(n,n)))


        road = Road(network=net, np_random=self.np_random, record_history=self.config["show_trajectories"])
        self.road = road

    def _make_vehicles(self) -> None:
        """
        Populate a road with several vehicles on the highway and on the merging lane, as well as an ego-vehicle.

        :return: the ego-vehicle
        """
        position_deviation = 2
        speed_deviation = 2

        # Ego-vehicle
        ego_lane = self.road.network.get_lane(("ser", "ses", 0))
        ego_vehicle = self.action_type.vehicle_class(self.road,
                                                     np.add(ego_lane.end,[0,5]),
                                                     speed=8,
                                                     heading=ego_lane.heading_at(ego_lane.end))
        try:            
            ego_vehicle.plan_route_to("wxr")
        except AttributeError:
            pass
        ego_vehicle.track_affiliated_lane = True
        self.road.vehicles.append(ego_vehicle)
        self.vehicle = ego_vehicle

        # Incoming vehicle
        destinations = ["exr", "sxr", "nxr"]
        other_vehicles_type = utils.class_from_path(self.config["other_vehicles_type"])
        vehicle = other_vehicles_type.make_on_lane(self.road,
                                                   ("we", "sx", 0),
                                                   longitudinal=5 + self.np_random.normal()*position_deviation,
                                                   speed=16 + self.np_random.normal() * speed_deviation)

        if self.config["incoming_vehicle_destination"] is not None:
            destination = destinations[self.config["incoming_vehicle_destination"]]
        else:
            destination = self.np_random.choice(destinations)
        vehicle.plan_route_to(destination)
        vehicle.randomize_behavior()
        self.road.vehicles.append(vehicle)

        # Other vehicles
        for i in list(range(1, 6)) + list(range(-1, 0)):
            vehicle = other_vehicles_type.make_on_lane(self.road,
                                                       ("we", "sx", 0),
                                                       longitudinal=20*i + self.np_random.normal()*position_deviation,
                                                       speed=16 + self.np_random.normal() * speed_deviation)
            vehicle.plan_route_to(self.np_random.choice(destinations))
            vehicle.randomize_behavior()
            self.road.vehicles.append(vehicle)

        # Entering vehicle
        vehicle = other_vehicles_type.make_on_lane(self.road,
                                                   ("eer", "ees", 0),
                                                   longitudinal=50 + self.np_random.normal() * position_deviation,
                                                   speed=16 + self.np_random.normal() * speed_deviation)
        vehicle.plan_route_to(self.np_random.choice(destinations))
        vehicle.randomize_behavior()
        self.road.vehicles.append(vehicle)


class RoundaboutTestEnv(RoundaboutEnv):
    def _reward(self, action: int) -> float:
        reward = 0
        #print(self.vehicle.position[0])

        #reward based on speed in the x-direction, becomes negative if car is driving backwards but in the right direction
        #max speed is +- 40
        #reward -= abs(self.vehicle.lane.local_coordinates(self.vehicle.position)[1])
        #print(self.vehicle.lane_index)
        #print(self.road.network.all_side_lanes(self.vehicle.lane_index))
        #if(isinstance(self.vehicle.lane, CircularLane)):
        #    print(self.vehicle.lane.tangent_vector(self.vehicle.position))
        print(self.vehicle.lane.distance(self.vehicle.position),self.vehicle.lane.heading_at(self.vehicle.position))
        #print(self.vehicle.heading,self.vehicle.lane.heading_at(self.vehicle.position))
        #print(self.vehicle.lane.start,self.vehicle.lane.end)
        #print(self.vehicle.position)
        #print(self.road.network.get_closest_lane_index(self.vehicle.position))
        
        return reward

class RoundaboutReward2(RoundaboutEnv):
    def _reward(self, action: int) -> float:
        reward = 0
        
        #punishment for driving on the left lane
        # lane = self.vehicle.target_lane_index[2] if isinstance(self.vehicle, ControlledVehicle) \
        #     else self.vehicle.lane_index[2]
        # reward -= lane
        #
        #take the difference in radians of the heading of the car and the heading of the road
        anglediff = min(abs(self.vehicle.heading-self.vehicle.lane.lane_heading(self.vehicle.position)),abs(self.vehicle.lane.lane_heading(self.vehicle.position))+abs(self.vehicle.heading))

        #effective speed divided by the distance to the lane
        if self.vehicle.speed > 0:
            #reward += abs(self.vehicle.position[1]-52)*np.cos(anglediff)*self.vehicle.speed/max(0.2,abs(self.vehicle.lane_distance))
            reward += np.cos(anglediff)*self.vehicle.speed/max(0.2,abs(self.vehicle.lane_distance))
      
        #scaling
        reward = reward/20
        
        #crash punishment
        if self.vehicle.crashed:
            return -10
        
        return reward

class DiscreteRoundaboutReward2(RoundaboutEnv):
    @classmethod
    def default_config(cls) -> dict:
        config = super().default_config()
        config.update({
            "observation": {
                "type": "Kinematics",
                #"features": ["presence", "x", "y", "vx", "vy", "long_off", "lat_off", "ang_off"],
            },
            "action": {
                "type": "DiscreteAction",
                "longitudinal": True,
                "lateral": True,
                "actions_per_axis": (3, 5)
            },
        })
        return config
    
    def _reward(self, action: int) -> float:
        reward = 0
        
        #punishment for driving on the left lane
        # lane = self.vehicle.target_lane_index[2] if isinstance(self.vehicle, ControlledVehicle) \
        #     else self.vehicle.lane_index[2]
        # reward -= lane
        #
        #take the difference in radians of the heading of the car and the heading of the road
        anglediff = min(abs(self.vehicle.heading-self.vehicle.lane.lane_heading(self.vehicle.position)),abs(self.vehicle.lane.lane_heading(self.vehicle.position))+abs(self.vehicle.heading))

        #effective speed divided by the distance to the lane
        if self.vehicle.speed > 0:
            #reward += abs(self.vehicle.position[1]-52)*np.cos(anglediff)*self.vehicle.speed/max(0.2,abs(self.vehicle.lane_distance))
            reward += np.cos(anglediff)*self.vehicle.speed/max(0.2,abs(self.vehicle.lane_distance))
      
        #scaling
        reward = reward/20
        
        #crash punishment
        if self.vehicle.crashed:
            return -10
        
        return reward

class DiscreteRoundaboutReward1(RoundaboutEnv):
    @classmethod
    def default_config(cls) -> dict:
        config = super().default_config()
        config.update({
            "observation": {
                "type": "Kinematics",
                #"features": ["presence", "x", "y", "vx", "vy", "long_off", "lat_off", "ang_off"],
            },
            "action": {
                "type": "DiscreteAction",
                "longitudinal": True,
                "lateral": True,
                "actions_per_axis": (3, 5)
            },
        })
        return config

register(
    id='roundabout-v0',
    entry_point='highway_env.envs:RoundaboutEnv',
)

register(
    id='roundabout-v1',
    entry_point='highway_env.envs:RoundaboutTestEnv',
)

register(
    id='roundabout-v2',
    entry_point='highway_env.envs:RoundaboutReward2',
)

register(
    id='roundabout-v3',
    entry_point='highway_env.envs:DiscreteRoundaboutReward2',
)

register(
    id='roundabout-v4',
    entry_point='highway_env.envs:DiscreteRoundaboutReward1',
)


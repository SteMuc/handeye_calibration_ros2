"""
Author: Shengyang Zhuang
Date Created: 2024-09-07
Description: ROS 2 program for obtaining robot transformation matrix from gripper to base

Copyright © 2024 Shengyang Zhuang. All rights reserved.
This script is part of the "Multi-Robot System Prototyping for Cooperative Control in Robot-Assisted Spine Surgery" project and is authored solely by Shengyang Zhuang.

Project Website: https://shengyangzhuang.github.io/mres_thesis/
Shengyang Zhuang Personal Website: https://shengyangzhuang.github.io/

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at:
    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

# Note: Please retain this header in derivative works.

BibTeX:
@mastersthesis{zhuang2024multirobot,
  author    = {Zhuang, Shengyang},
  title     = {Multi-Robot System Prototyping for Cooperative Control in Robot-Assisted Spine Surgery},
  school    = {Imperial College London},
  year      = {2024},
}
"""


import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, DurabilityPolicy
from tf2_msgs.msg import TFMessage
from sensor_msgs.msg import JointState
from std_msgs.msg import String

import numpy as np
from scipy.spatial.transform import Rotation as R
import yaml
import sys
import select

# Create a QoS profile for subscribing to /tf_static
qos_profile = QoSProfile(depth=10, durability=DurabilityPolicy.TRANSIENT_LOCAL)


class RobotTransformNode(Node):
    def __init__(self):
        super().__init__('robot_transform_node')
        self.subscription_tf = self.create_subscription(TFMessage, '/tf', self.listener_callback_tf, 10)
        self.subscription_tf_static = self.create_subscription(TFMessage,'/tf_static', self.listener_callback_tf_static, qos_profile)
        self.transformations = {}
        self.pose_count = 0
        self.subscription_keypress = self.create_subscription(String, 'keypress_topic', self.keypress_callback, 10)
        
        with open('src/handeye_calibration/handeye_realsense/config.yaml', 'r') as file:
            config = yaml.safe_load(file)
        self.robot_data_file_name = config["robot_data_file_name"]
        self.base_link = config["base_link"]
        self.ee_link = config["ee_link"]

    def quaternion_to_rotation_matrix(self, x, y, z, w):
        """ Convert a quaternion into a full three-dimensional rotation matrix. """
        return R.from_quat([x, y, z, w]).as_matrix()

    def listener_callback_tf(self, msg):
        """ Handle incoming transform messages. """
        for transform in msg.transforms:
            if transform.child_frame_id and transform.header.frame_id:
                self.transformations[(transform.header.frame_id, transform.child_frame_id)] = transform

    def listener_callback_tf_static(self, msg):
        """ Handle incoming transform messages. """
        for transform in msg.transforms:
            if transform.child_frame_id and transform.header.frame_id:
                self.transformations[(transform.header.frame_id, transform.child_frame_id)] = transform
        self.get_logger().info("Subscribed to /tf_static successfully")


    def get_full_transformation_matrix(self):
        T = np.eye(4)  # Start with the identity matrix
        link_order = [
            ('base_link', 'base_link_inertia'), ('base_link_inertia', 'shoulder_link'), 
            ('shoulder_link', 'upper_arm_link'), ('upper_arm_link', 'forearm_link'), 
            ('forearm_link', 'wrist_1_link'), ('wrist_1_link', 'wrist_2_link'), 
            ('wrist_2_link', 'wrist_3_link'),
            ('wrist_3_link', 'flange'),
            ('flange', 'tool0'),
        ]
        for (frame_id, child_frame_id) in link_order:
            if (frame_id, child_frame_id) in self.transformations:
                trans = self.transformations[(frame_id, child_frame_id)].transform
                translation = [trans.translation.x, trans.translation.y, trans.translation.z]
                rotation = [trans.rotation.x, trans.rotation.y, trans.rotation.z, trans.rotation.w]
                T_local = np.eye(4)
                T_local[:3, :3] = self.quaternion_to_rotation_matrix(*rotation)
                T_local[:3, 3] = translation
                T = np.dot(T, T_local)

        return T

    def save_transformation_to_yaml(self, rotation_matrix, translation_vector):
        """ Append the rotation matrix and translation vector to a YAML file and print them. """
        # Load existing data from YAML if file exists and is not empty
        yaml_file_path = self.robot_data_file_name
        try:
            with open(yaml_file_path, 'r') as file:
                data = yaml.safe_load(file) or {'poses': []}  # Use existing data or initialize if empty
        except FileNotFoundError:
            data = {'poses': []}  # Initialize if file does not exist

        # Append new pose data
        data['poses'].append({
            'rotation': rotation_matrix.tolist(),
            'translation': translation_vector.tolist()
        })

        # Write updated data back to YAML
        with open(yaml_file_path, 'w') as file:  # 'w' to overwrite existing file
            yaml.dump(data, file, default_flow_style=False)

        self.pose_count += 1  # Increment pose counter
        print(f"Pose {self.pose_count}:")
        print("Rotation Matrix:")
        print(rotation_matrix)
        print("Translation Vector:")
        print(translation_vector)
        self.get_logger().info(f'Transformation for Pose {self.pose_count} appended to robot_data_realsense.yaml')
    
    def keypress_callback(self, msg):
        key = msg.data
        if key == 'q':
            T = self.get_full_transformation_matrix()
            R_gripper2base = T[:3, :3]
            t_gripper2base = T[:3, 3]
            self.save_transformation_to_yaml(R_gripper2base, t_gripper2base)
        elif key == 'e':
            self.get_logger().info("Ending program...")
            rclpy.shutdown()


def main(args=None):
    rclpy.init(args=args)
    robot_transform_node = RobotTransformNode()

    try:
        rclpy.spin(robot_transform_node)
    finally:
        robot_transform_node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

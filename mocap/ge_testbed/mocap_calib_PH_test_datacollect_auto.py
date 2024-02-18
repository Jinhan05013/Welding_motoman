from copy import deepcopy
import sys
sys.path.append('toolbox/')
from utils import *
from robot_def import * 

from general_robotics_toolbox import *
from RobotRaconteur.Client import *
from threading import Thread
import numpy as np
import time
import yaml
from fanuc_motion_program_exec_client import *
from MocapPoseListener import *
import pickle

class CalibRobotPH:
    def __init__(self,mocap_cli,robot) -> None:
        
        self.mocap_cli = mocap_cli

        self.robot = robot
        # self.calib_marker_ids = robot.calib_markers_id
        self.calib_marker_ids = robot.tool_markers_id
        print('Calib ID:',self.calib_marker_ids)
        self.base_markers_ids = robot.base_markers_id
        self.base_rigid_id = robot.base_rigid_id

        # mocap listener
        all_ids=[]
        all_ids.extend(self.calib_marker_ids)
        all_ids.extend(self.base_markers_ids)
        all_ids.append(self.base_rigid_id)
        all_ids.append(robot.tool_rigid_id)
        all_ids.append("marker10_rigid0")
        self.mpl_obj = MocapFrameListener(self.mocap_cli,all_ids,'world',use_quat=True)
    
    def run_datacollect_sync(self,rob_IP=None,paths=[],rob_speed=3,waittime=1,
                  raw_data_dir='',split_motion=2,uframe_num=1,utool_num=1,robot_group=1):
        
        client = FANUCClient(rob_IP)
        read_N=1
        
        input("Press Enter and the robot will start moving.")
        
        tp= TPMotionProgram(tool_num=utool_num,uframe_num=uframe_num)
        tp.setIO('DO',10,False)
        for q in paths:
            jt = jointtarget(robot_group,uframe_num,utool_num,q,[0]*6)
            tp.moveJ(jt,rob_speed,'%',-1) # moveJ does not support coordinated motion
            # tp.moveJ(jt,rob_speed,'%',-1) # moveJ does not support coordinated motion
            # tp.setIO('DO',10,True)
            # tp.waitIO('DO',10,False)
        client.execute_motion_program(tp,record_joint=False,non_block=True)
        
        pose_cnt=0
        base_T=[]
        tool_T=[]
        marker_T={}
        robot_joint=[]
        while True:
            res_io=client.read_ioport('DOUT',10)
            
            if res_io:
                self.mpl_obj.run_pose_listener()
                joint_exe = client.get_joint_angle(read_N=read_N)
                self.mpl_obj.stop_pose_listener()
                mocap_curve_p,mocap_curve_R,mocap_timestamps,curve_cond = self.mpl_obj.get_frames_traj_cond()
                
                # base rigid
                for k in range(len(mocap_curve_p[self.robot.base_rigid_id])):
                    this_stamp_data=np.append(mocap_curve_p[self.robot.base_rigid_id][k],\
                                            mocap_curve_R[self.robot.base_rigid_id][k])
                    this_stamp_data=np.append(this_stamp_data,curve_cond[self.robot.base_rigid_id][k])
                    base_T.append(this_stamp_data)
                
                # tool rigid
                for k in range(len(mocap_curve_p[self.robot.tool_rigid_id])):
                    this_stamp_data=np.append(mocap_curve_p[self.robot.tool_rigid_id][k],\
                                            mocap_curve_R[self.robot.tool_rigid_id][k])
                    this_stamp_data=np.append(this_stamp_data,curve_cond[self.robot.tool_rigid_id][k])
                    tool_T.append(this_stamp_data)
                
                # tool marker
                for mkr in self.robot.tool_markers_id:
                    print(len(mocap_curve_p[mkr]))
                    for k in range(len(mocap_curve_p[mkr])):
                        this_stamp_data=np.append(mocap_curve_p[mkr][k],\
                                                mocap_curve_R[mkr][k])
                        this_stamp_data=np.append(this_stamp_data,curve_cond[mkr][k])
                        if mkr in marker_T.keys():
                            marker_T[mkr].append(this_stamp_data)
                        else:
                            marker_T[mkr]=[this_stamp_data]
                
                # robot q
                robot_joint.extend(joint_exe)
                
                if pose_cnt %50==0:
                    np.savetxt(raw_data_dir+'_robot_q_raw.csv',robot_joint,delimiter=',')
                    np.savetxt(raw_data_dir+'_tool_T_raw.csv',tool_T,delimiter=',')
                    np.savetxt(raw_data_dir+'_base_T_raw.csv',base_T,delimiter=',')
                    with open(raw_data_dir+'_marker_raw.pickle', 'wb') as handle:
                        pickle.dump(marker_T, handle, protocol=pickle.HIGHEST_PROTOCOL)

                print("Q raw num:",len(robot_joint))
                print("Tool T raw num:",len(tool_T))
                print("Base T raw num:",len(base_T))
                print("Collect pose:",pose_cnt+1)
                pose_cnt+=1
                print("================================================")
                
                client.set_ioport('DOUT',10,False)
                
                if pose_cnt==len(paths):
                    break
            else:
                time.sleep(0.1)
        # last save
        np.savetxt(raw_data_dir+'_robot_q_raw.csv',robot_joint,delimiter=',')
        np.savetxt(raw_data_dir+'_tool_T_raw.csv',tool_T,delimiter=',')
        np.savetxt(raw_data_dir+'_base_T_raw.csv',base_T,delimiter=',')
        with open(raw_data_dir+'_marker_raw.pickle', 'wb') as handle:
            pickle.dump(marker_T, handle, protocol=pickle.HIGHEST_PROTOCOL)

def calib_R2():

    config_dir='config/'
    robot_name='LRMATE200id'
    tool_name='ge_R2_tool'
    robot_marker_dir=config_dir+robot_name+'_marker_config/'
    tool_marker_dir=config_dir+tool_name+'_marker_config/'
    uframe_num=4
    utool_num=1
    robot_group=2

    dataset_date = '0801'
    print("Dataset Date:",dataset_date)
    
    if dataset_date=='':
        robot=robot_obj(robot_name,def_path=config_dir+robot_name+'_robot_default_config.yml',tool_file_path=config_dir+tool_name+'.csv',\
    base_marker_config_file=robot_marker_dir+robot_name+'_marker_config.yaml',tool_marker_config_file=tool_marker_dir+tool_name+'_marker_config.yaml')
    else:
        robot=robot_obj(robot_name,def_path=config_dir+robot_name+'_robot_default_config.yml',tool_file_path=config_dir+tool_name+'.csv',\
        base_marker_config_file=robot_marker_dir+robot_name+'_'+dataset_date+'_marker_config.yaml',tool_marker_config_file=tool_marker_dir+tool_name+'_'+dataset_date+'_marker_config.yaml')

    mocap_url = 'rr+tcp://localhost:59823?service=phasespace_mocap'
    mocap_cli = RRN.ConnectService(mocap_url)
    
    rob_ip='192.168.1.101'

    calib_obj = CalibRobotPH(mocap_cli,robot)

    # calibration
    q2_up=50
    q2_low=-55
    q3_up_sample = np.array([[-55,-40],[0,10],[50,50]]) #[[q2 q3]]
    q3_low_sample = np.array([[-55,-70],[0,-50],[50,0]]) #[[q2 q3]]
    d_angle = 5 # 5 degree
    dq_sample = [[0,0,0,0,0,0],\
          [1,0,0,-0,-0,0],[0,1,0,0,0,0],\
          [0,0,1,0,0,0],[0,0,0,1,0,0],\
          [0,0,0,0,1,0],[0,0,0,0,0,1]]
    scale=1
    dq_sample = np.array(dq_sample)*scale

    target_q_zero = np.array([1,0,0,1,1,1])

    # speed
    rob_speed=3
    waittime=0.5 # stop 0.5 sec for sync

    test_qs = []
    sample_q = np.radians([[-8,-13,-42,0,-58,-2],[-51,-5,-33,4,-56,37],\
                        [-24,-30,-60,4,-42,38],[-24,-12,-41,4,-58,38],\
                        [-8,-13,-42,0,-58,-2]])
    sample_N = [100,100,100,100] # len(sample_q)-1
    # sample_N = [2,2,2,2] # len(sample_q)-1
    for i in range(len(sample_N)):
        start_T = robot.fwd(sample_q[i])
        end_T = robot.fwd(sample_q[i+1])
        k,dtheta = R2rot(np.matmul(start_T.R.T,end_T.R))
        dp_vector = end_T.p-start_T.p
        for n in range(sample_N[i]):
            this_R=np.matmul(start_T.R,rot(k,dtheta/sample_N[i]*n))
            this_p=start_T.p+dp_vector/sample_N[i]*n
            this_q=robot.inv(this_p,this_R,last_joints=sample_q[i])[0]
            test_qs.append(np.round(np.degrees(this_q),4))
    print(test_qs)
    q_paths=test_qs
    print("total pose:",len(q_paths))
    print("Data Base:",dataset_date)
    # exit()

    # collecting raw data
    raw_data_dir='testing_data/test_data'
    #####################

    calib_obj.run_datacollect_sync(rob_ip,q_paths,rob_speed=rob_speed,waittime=waittime\
                        ,raw_data_dir=raw_data_dir,uframe_num=uframe_num,utool_num=utool_num,robot_group=robot_group) # save calib config to file
    print("Collect PH data done")

def calib_R1():
    
    config_dir='config/'
    robot_name='M10ia'
    tool_name='ge_R1_tool'
    robot_marker_dir=config_dir+robot_name+'_marker_config/'
    tool_marker_dir=config_dir+tool_name+'_marker_config/'
    uframe_num=4
    utool_num=1
    robot_group=1

    dataset_date = ''
    print("Dataset Date:",dataset_date)
    
    if dataset_date=='':
        robot=robot_obj(robot_name,def_path=config_dir+robot_name+'_robot_default_config.yml',tool_file_path=config_dir+tool_name+'.csv',\
    base_marker_config_file=robot_marker_dir+robot_name+'_marker_config.yaml',tool_marker_config_file=tool_marker_dir+tool_name+'_marker_config.yaml')
    else:
        robot=robot_obj(robot_name,def_path=config_dir+robot_name+'_robot_default_config.yml',tool_file_path=config_dir+tool_name+'.csv',\
        base_marker_config_file=robot_marker_dir+robot_name+'_'+dataset_date+'_marker_config.yaml',tool_marker_config_file=tool_marker_dir+tool_name+'_'+dataset_date+'_marker_config.yaml')

    mocap_url = 'rr+tcp://localhost:59823?service=phasespace_mocap'
    mocap_cli = RRN.ConnectService(mocap_url)
    
    # rob_ip='127.0.0.1'
    rob_ip='192.168.0.1'

    calib_obj = CalibRobotPH(mocap_cli,robot)
    
    # speed
    rob_speed=10
    waittime=0.5 # stop 0.5 sec for sync

    test_qs = []
    sample_q = np.radians([[-10,-31,-72,2,-38,-13],[-70,-8,-61,-6,-28,13],\
                        [-70,-22,-26,-3,-79,9],[-5,-43,-36,6,-91,-22],\
                        [-10,-31,-72,2,-38,-13]])
    sample_N = [100,100,100,100] # len(sample_q)-1
    # sample_N = [2,2,2,2] # len(sample_q)-1
    for i in range(len(sample_N)):
        start_T = robot.fwd(sample_q[i])
        end_T = robot.fwd(sample_q[i+1])
        k,dtheta = R2rot(np.matmul(start_T.R.T,end_T.R))
        dp_vector = end_T.p-start_T.p
        for n in range(sample_N[i]):
            this_R=np.matmul(start_T.R,rot(k,dtheta/sample_N[i]*n))
            this_p=start_T.p+dp_vector/sample_N[i]*n
            this_q=robot.inv(this_p,this_R,last_joints=sample_q[i])[0]
            test_qs.append(np.round(np.degrees(this_q),4))
    q_paths=test_qs
    print("total pose:",len(q_paths))
    print("Data Base:",dataset_date)
    # exit()

    # collecting raw data
    raw_data_dir='testing_data/test_data'
    #####################

    calib_obj.run_datacollect_sync(rob_ip,q_paths,rob_speed=rob_speed,waittime=waittime\
                        ,raw_data_dir=raw_data_dir,uframe_num=uframe_num,utool_num=utool_num,robot_group=robot_group) # save calib config to file
    print("Collect PH data done")


if __name__=='__main__':

    calib_R1()
    # calib_R2()
    # calib_S1()
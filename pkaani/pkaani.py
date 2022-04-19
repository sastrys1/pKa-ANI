import torch
import torchani
import os
import math
import sys
import numpy as np
import csv
import joblib 

from .ani_descriptors import pdb_arrays,get_titratable,get_indices,get_desc_arrays
from .ase_io_proteindatabank_mod import read_proteindatabank



def calculate_pka(pdbfiles):

    
    # device to run the training
    device = torch.device('cpu')
    
 
    #FEATURES
    tyr_features=joblib.load(os.path.join(os.path.dirname(__file__),'models/FTYR.joblib'))
    asp_features=joblib.load(os.path.join(os.path.dirname(__file__),'models/FASP.joblib'))
    glu_features=joblib.load(os.path.join(os.path.dirname(__file__),'models/FGLU.joblib'))
    lys_features=joblib.load(os.path.join(os.path.dirname(__file__),'models/FLYS.joblib'))
    his_features=joblib.load(os.path.join(os.path.dirname(__file__),'models/FHIS.joblib'))
    
    #MODELS
    asp_model=joblib.load(os.path.join(os.path.dirname(__file__),'models/ASP_ani2x_FINAL_MODEL_F100.joblib'))
    glu_model=joblib.load(os.path.join(os.path.dirname(__file__),'models/GLU_ani2x_FINAL_MODEL_F75.joblib'))
    his_model=joblib.load(os.path.join(os.path.dirname(__file__),'models/HIS_ani2x_FINAL_MODEL_F100.joblib'))
    lys_model=joblib.load(os.path.join(os.path.dirname(__file__),'models/LYS_ani2x_FINAL_MODEL_F25.joblib'))
    tyr_model=joblib.load(os.path.join(os.path.dirname(__file__),'models/TYR_ani2x_FINAL_MODEL_F25.joblib'))
    
    #######################################################################
    
    
    #call ani
    ani = torchani.models.ANI2x(periodic_table_index=True)
    
    
    pkaressize=0
    
    print('Loaded pKa-ANI Models and ANI-2x...')    
    for fpdb in pdbfiles:
        print('Calculating pKa for %s' % fpdb)    
        
        basename=fpdb.rsplit('.', 1)[0]
        infile=str(basename)+".pdb"
        
        flog=basename+"_pka.log"
        fo=open(flog,"w") 
        writer = csv.writer(fo,delimiter='\t')
        writer.writerow(['Residue', 'Chain', 'pKa'])
        
        
        #read pdb, and convert to ani type
        atoms=read_proteindatabank(infile, read_arrays=True)
        res,res_no,a_type,a_sym,a_no,pos,chainid,type_atm = pdb_arrays(atoms)
      
        chainid=np.array(chainid)
       
        sptensor=torch.tensor([a_no], device=device)
        pos=torch.tensor(pos,dtype=torch.float32)
        coords=torch.reshape(pos, (1, len(a_no),3))
        
        species_coordinates = ani.species_converter((sptensor, coords))
        aev = ani.aev_computer(species_coordinates)[1]
            
        #find titratable residues
        pkares,pkach=get_titratable(a_type,res,res_no,chainid)
        
        #   divide atoms into groups by residue number
        #   this will be used to get activation and aev indices
        #   ca_list: the indices of CA atoms
        #   chlist : the chain IDs
        #   pdball_resi: atom indices per residue
        #   after having thesem we will only chose if the residue
        #   is titratable
        #
        #   i.e.
        #       ca_list  = [6, 7, 8] 
        #       pdball_resi = [array([0, 1, 2, 3, 4, 5, 6, 7]), 
        #                   array([ 8,  9, 10, 11]), 
        #                   array([12, 13, 14, 15, 16, 17, 18, 19, 20])]
        
        ca_list=[]
        chlist=[]
        for i,a in enumerate(a_type):
            if((str(a)=='CA') and type_atm[i].strip()=='ATOM'):
                ca_list.append(res_no[i])
                chlist.append(chainid[i])
      
    
        
        pdball_resi=[]
        for i,r in enumerate(ca_list):
            ilist=np.array(np.where((res_no == r) & (chainid == chlist[i])))
            pdball_resi.append(ilist.flatten())
        
        nk,ck,ok=0,0,0 # counters for activation indices
      
        #GET ACTIVATION AND AEV INDICES
        #FOR ALL ATOMS
        all_acti=[]
        all_aevi=[]
    
        for k,index in enumerate(pdball_resi):
            activation_i,aev_i,nk,ck,ok=get_indices(index,a_type,a_no,nk,ck,ok)
            all_acti.append(activation_i)
            all_aevi.append(aev_i)               
    
    
        #now we are looping over residues
        #then if the residue is titratable 
        # we get aev, NN activation, and atom indices    
        for i,r in enumerate(ca_list):
            if(r in list(pkares)):
               pkaressize=pkaressize+1
               res_aevi=all_aevi[i]           
               res_acti=all_acti[i]
               index=pdball_resi[i]
               
               lres=str(res[index[0]].strip())
               lchid=str(chainid[index[0]]).strip()
               lrnum=str(res_no[index[0]])
    
               mychain=lchid
               if not lchid: mychain='A'
      
               a_symbols=[]
               for i in res_aevi: a_symbols.append(a_sym[i])
      
               
               ani_descriptors,features=get_desc_arrays(ani,species_coordinates,aev,res_acti,res_aevi,a_symbols,a_type)
    
    
               checklist=[]
               if(lres=='GLU'):
                  ani_descriptors_model=[] 
                  checklist=glu_features
                  model=glu_model
               if(lres=='ASP'):
                  ani_descriptors_model=[]
                  checklist=asp_features
                  model=asp_model
               if(lres=='LYS'):
                  ani_descriptors_model=[]
                  checklist=lys_features
                  model=lys_model
               if(lres=='HIS' or lres=='HID' or lres=='HIE'):
                  ani_descriptors_model=[]
                  checklist=his_features
                  model=his_model
               if(lres=='TYR'):
                  ani_descriptors_model=[]
                  checklist=tyr_features
                  model=tyr_model
    
    
               for i,fl in enumerate(features):
                   if(str(fl) in checklist):
                       ani_descriptors_model.append(ani_descriptors[i])
    
               ani_descriptors_model=np.array(ani_descriptors_model)
               ani_descriptors=ani_descriptors_model 
               
               X = np.reshape(ani_descriptors,(1, ani_descriptors.size))
      
               estimate_pka=model.predict(X)
    
               wres=lres+"-"+lrnum
               writer.writerow([wres,mychain,'{:2.2f}'.format(estimate_pka[0])])
    
        
        fo.close()           
       
        #rename PDB file names to get them in proper order
        os.rename(infile,str(basename)+"_prep.pdb")
        #os.rename(str(basename)+"_0.pdb",infile)


    

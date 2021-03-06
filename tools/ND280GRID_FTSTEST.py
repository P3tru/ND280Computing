#!/usr/bin/env python

"""

Handy functions to make using the GRID a little more bearable.

"""

from time import sleep
import sys
import re
import tempfile
import os
import optparse
import shutil
import pexpect
import time
import datetime
from datetime import datetime
from datetime import date
import random
import traceback
import subprocess
from subprocess import Popen, PIPE
import signal
from hashlib import sha1
from uuid import uuid1


########################
## Master dictionary containing se : [ root, fts2Channel, hasSpaceToken ] bindings
se_master={'srm-t2k.gridpp.rl.ac.uk'   :['srm://srm-t2k.gridpp.rl.ac.uk/castor/ads.rl.ac.uk/prod/t2k.org/nd280/',  'RALLCG2',              True ],                                                   
           'se03.esc.qmul.ac.uk'       :['srm://se03.esc.qmul.ac.uk/t2k.org/nd280/',                               'UKILT2QMUL',           True ],  # confirmed default location for new data     
           'gfe02.grid.hep.ph.ic.ac.uk':['srm://gfe02.grid.hep.ph.ic.ac.uk/pnfs/hep.ph.ic.ac.uk/data/t2k/nd280/',  'UKILT2ICHEP',          True ],                                                
           'hepgrid11.ph.liv.ac.uk'    :['srm://hepgrid11.ph.liv.ac.uk/dpm/ph.liv.ac.uk/home/t2k.org/nd280/',      'UKINORTHGRIDLIVHEP',   True ],                                                
           'lcgse0.shef.ac.uk'         :['srm://lcgse0.shef.ac.uk/dpm/shef.ac.uk/home/t2k.org/nd280/',             'UKINORTHGRIDSHEFHEP',  True ],                                                
           't2se01.physics.ox.ac.uk'   :['srm://t2se01.physics.ox.ac.uk/dpm/physics.ox.ac.uk/home/t2k.org/nd280/', 'UKISOUTHGRIDOXHEP',    False], # not yet implemented...                      
           'ccsrm02.in2p3.fr'          :['srm://ccsrm02.in2p3.fr/pnfs/in2p3.fr/data/t2k/t2k.org/nd280/',           'IN2P3CC',              False], # broke SRM                                   
           'fal-pygrid-30.lancs.ac.uk' :['srm://fal-pygrid-30.lancs.ac.uk/dpm/lancs.ac.uk/home/t2k.org/nd280/',    'UKINORTHGRIDLANCSHEP', True ],                                                
           't2ksrm.nd280.org'          :['srm://t2ksrm.nd280.org/nd280data/',                                      'CATRIUMFT2K',          False],                                               
           'srmv2.ific.uv.es'          :['srm://srmv2.ific.uv.es/lustre/ific.uv.es/grid/t2k.org/nd280/',           '',                     True ],                                                
           'srm.pic.es'                :['srm://srm.pic.es/pnfs/pic.es/data/t2k.org/nd280/',                       'PIC',                  True ],  # confirmed default location for new data     
           'kek2-se01.cc.kek.jp'       :['srm://kek2-se01.cc.kek.jp/t2k.org/nd280/',                               'JPKEKCRC02',           False],                                               
           'kek2-se.cc.kek.jp'         :['srm://kek2-se.cc.kek.jp/t2k.org/nd280/',                                 'JPKEKCRC02',           False]                                               
          }

# SRM root directories
se_roots={}

# FTS channel name associated with each SRM
se_channels={}

# Sites enabled with T2KORGDISK space token
se_spacetokens={}

# Fill from master
for se, [root,channel,token] in se_master.iteritems():
    se_roots      [se] = root
    se_channels   [se] = channel
    se_spacetokens[se] = token

def GetSEChannels():
    return se_channels

def GetSERoots():
    return se_roots



########################
## The ND280 detectors
ND280DETECTORS = ['ECAL','FGD','ND280','P0D','SMRD','TPC']


########################
## The non runND280 job types
NONRUNND280JOBS = ['HADD','FlatTree','MiniTree']


########################
## Function to determine number of active processes from a list
def countActiveProcesses(processList=[]):
    return [ p.poll() for p in processList ].count(None)


########################
## Function to wait for processes
def processWait(processList=[],limit=0):

    while 1:
        nActive = countActiveProcesses(processList)

        if nActive < limit or not nActive:
            break

        print '%3d active processes ... sleeping until there are < %d ...' % (nActive,limit)
        time.sleep(60)

    return

########################
## Compile the SE root-directory dictionary live from lcg-infosites rather than 
## hard coding
def GetLiveSERoots():
    print 'Getting live SE root directories'

    se_roots_live={}

    for se in GetListOfSEs():
        se_roots_live[se]=GetTopLevelDir(se)

    return se_roots_live

########################
## Get top level (../t2k.org/) directory from storage element
## Not perfect, some read/write issues on some SEs, handled by exception
def GetTopLevelDir(storageElement):
    print 'GetTopLevelDir'

    # Default empty string
    top_level_dir=''

    # Use a local test file
    testFileName = 'lcgCrTestfile.'+str(os.getpid())
    command = "dd if=/dev/zero of="+testFileName+" bs=1048576 count=1"
    print command
    os.system(command)
        
    # Make sure test file is not already registered on LFC
    command= "lcg-del --vo t2k.org -a lfn:/grid/t2k.org/test/"+testFileName+" </dev/null >/dev/null 2>&1"
    os.system(command)
    
    try:
        # Register test file on storage element using relative path name, returns GUID
        # Entry in LFC in the test directory of /grid/t2k.org/
        command= "lcg-cr --vo t2k.org -d " + storageElement + " -P "+testFileName+" -l lfn:/grid/t2k.org/test/"+testFileName+" file:"+testFileName
        lines,errors = runLCG(command,is_pexpect=False)
        if errors: raise Exception

                
        # Use GUID to retrieve data path to test file, and hence top level directory
        command= "lcg-lr --vo t2k.org " + rmNL(lines[0])
        lines,errors = runLCG(command,is_pexpect=False)
        if errors: raise Exception
        
        surl = lines[0]
        top_level_dir=rmNL(surl.replace(testFileName,""))
 
    # Exception handles access errors, bit of a cludge
    except:
        # Carry on regardless, get data path with error
        print 'Exception: '+rmNL(errors[0])
        top_level_dir=rmNL(errors[0].split('lcgCr')[0])

        command = 'lcg-ls --vo t2k.org '+top_level_dir+testFileName
        lines,errors = runLCG(command,is_pexpect=False)
        if lines:
            command=command.replace('lcg-ls','lcg-del -l')
            runLCG(command,is_pexpect=False)
            
    # Clean up, don't worry about errors
    os.system("rm -f "+testFileName)
    os.system("lcg-del --vo t2k.org -a lfn:/grid/t2k.org/test/"+testFileName)

    # Last ditch, use se_roots but truncate nd280/ subdirectory
    if 'error' in top_level_dir or not 'srm://' in top_level_dir:
        top_level_dir = se_roots[storageElement].replace('nd280/','')

    # Make sure there is only one trailing slash
    top_level_dir = top_level_dir.rstrip('//')
    top_level_dir += '/'

    print  top_level_dir
    return top_level_dir

########################
## Get list of Storage Elements
def GetListOfSEs():
    print 'GetListOfSEs'
    
    try:
        command= "lcg-infosites --vo t2k.org se"
        p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        lines  = p.stdout.readlines()
        errors = p.stderr.readlines()

        if errors: raise Exception
    
        seList=[]
        # skip first 2 lines
        for line in lines[2:]:
            word = line.split()
            seName = word[3]

            # Ignore following (for now)
            if 'manchester'          in seName: continue
            if 'heplnx204'           in seName: continue
            if 'se04.esc.qmul.ac.uk' in seName: continue

            # Append se to list
            seList.append(seName)

        # return unique elements only
        return list(set(seList))
    except:
        print 'Could not get list of SEs'
        print '\n'.join(errors)
        return []

########################
## Get list of Computing Elements
def GetListOfCEs():
    print 'GetListOfCEs'

    try:
        command= "lcg-infosites --vo t2k.org ce"    
        p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        lines  = p.stdout.readlines()
        errors = p.stderr.readlines()
 
        if errors: raise Exception
        
        ceList=[]
        # Skip first 2 lines
        for line in lines[2:]:
            words = line.split()
            # read 6th column
            words = words[5].split('/');
            ceList.append(words[0])
        # Only return one of each
        return list(set(ceList))
    except:
        print 'Could not get list of CEs'
        print '\n'.join(errors)
        return []

########################
## Check if CE is CREAM enabled
def IsCREAMed(ce):

    command= "glite-ce-allowed-submission " + ce
    p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
    lines  = p.stdout.readlines()
    errors = p.stderr.readlines()
    
    for line in lines:
        if "this CREAM CE is enabled" in line:
            return True
    return False

########################
## Print Storage Element Disk Usage
def PrintSEDiskUsage():
    
    command= "lcg-infosites --vo t2k.org se"
    p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
    lines  = p.stdout.readlines()
    errors = p.stderr.readlines()
    
    print 'Free (TB)  Used(TB)  SE'
    print '-------------------------------------------------'
    
    # skip first 2 lines
    if lines:
        for line in lines[2:]:
        
            words = line.split()
            seFree = words[0]
            seUsed = words[1]
            seName = words[3]
            
            # Ignore manchester and heplnx204.pp.rl.ac.uk (for now)
            if 'manchester'       in seName: continue
            if 'heplnx204'        in seName: continue

            # Numbers are 10E3 (rather than 2E10)
            KbToTB = 1E-9

            if 'n.a' in seFree:
                seFree = 0
            else:
                seFree = float(seFree)*KbToTB
            if 'n.a' in seUsed:
                seUsed = 0
            else:
                seUsed = float(seUsed)*KbToTB

            # Ignore if free and used both 0
            if seFree == 0 and seUsed == 0: continue
            
            print '%9.2f %9.2f  %s' % (seFree,seUsed,seName)
    else:
        if errors:
            print '\n'.join(errors)

########################
## Print Storage Element Space Usage
def PrintSESpaceUsage():
    
    command= "lcg-infosites --vo t2k.org space"
    p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
    lines  = p.stdout.readlines()
    errors = p.stderr.readlines()

    print '    Free     Used     Free     Used              Tag SE'
    print '  Online   Online Nearline Nearline (TB)                   '
    print '--------------------------------------------------------------------------------'
    
    # skip first 2 lines
    if lines:
        for line in lines[3:]:
        
            words = line.split()
            onlineFree   = float(words[0])/1024.
            onlineUsed   = float(words[1])/1024.
            nearlineFree = float(words[3])/1024.
            nearlineUsed = float(words[4])/1024.
            tag          = words[6]
            se           = words[7]
            
            
            # Ignore if free and used both 0|1
            if onlineUsed <= 1 and onlineUsed <= 1: continue
            
            
            print '%8.2f %8.2f %8.2f %8.2f %16s %s' % (onlineFree,onlineUsed,nearlineFree,nearlineUsed,tag,se)
    else:
        if errors:
            print '\n'.join(errors)

########################
## List active FTS transfers:
def GetFTS2ActiveTransferList(channel = ''):

    Fail = [],[]

    try:

        transfers=[]
        statuses =[]

        command = "fts-transfer-list -s " + os.getenv("FTS_SERVICE")
        if channel: command += ' -c '+channel

        lines,errors = runLCG(command)

        if errors: 
            print "Couldn't access "+channel
            return Fail

        transfers = [ rmNL(line.split('\t')[0]) for line in lines ]
        statuses  = [ rmNL(line.split('\t')[1]) for line in lines if len(line.split('\t'))>1 ]

        return transfers,statuses

    except:
        traceback.print_exc()
        return Fail

########################
## FTS2 transfer statuses:
fts2_active_list  = ['Active','Pending','Ready','Finishing','Submitted','Hold','Waiting']
fts2_finished_list= ['Done','Finished','FinishedDirty']
fts2_failed_list  = ['Canceled','Failed']

### FTS3 transfer statuses
fts3_active_list  = ['ACTIVE','PENDING','READY','SUBMITTED']
fts3_finished_list= ['FINISHED','FINISHEDDIRTY']
fts3_failed_list  = ['CANCELLED','FAILED']


########################
## List active FTS transfers:
def GetActiveTransferList(source='',dest=''):

    Fail = [],[]

    if source not in se_roots.keys() or (dest and dest not in se_roots.keys()):
        print 'Invalid source/destination : source=%s dest=%s' % (source,dest)
        print 'Please choose from the following:\n\n\t%s'      % ('\n\t'.join(se_roots.keys()))
        return Fail

    try:

        transfers=[]
        statuses =[]

        command = 'fts-transfer-list -o t2k.org -s %s --source_se %s' % (os.getenv("FTS_SERVICE"),source)
        if dest: command += ' --dest_se %s' % (dest)
        lines,errors = runLCG(command)
        #are no FTS transfers but instead the line
        #'No data have been found for the specified state(s) and/or user VO/VOMS roles.'
        if errors: 
            print "Error Couldn't access "+channel
            return Fail
        if "No data have been found" in lines[0]:
            print "No active channels "+channel
            #return empty transfer,statuses lists
            return transfers,statuses
        else:
            index=0
            for line in lines:
                if "Request" in line:
                    transfers.append(rmNL(line.split(' ')[2]))
                if "Status" in line:
                    statuses.append(rmNL(line.split(' ')[1]))
                index+=1
                
            #parse the lines.  Much more annoying that with glite-transfer-list
            #format ['Request ID: 2fe4b204-6645-11e7-aaac-001dd8b71ccb', 'Status: ACTIVE', '', 'Request ID: 702331c4-6645-11e7-bf66-001dd8b71cf7', 'Status: SUBMITTED', '' ...]
        
        return transfers,statuses

    except:
        traceback.print_exc()
        return Fail

########################
## Get status of an FTS transfer:
def GetTransferStatus(transfer='', SOURCE='', DEST=''):

    Fail = '','','' 
    if not transfer: return Fail

    if SOURCE : print 'Looking for SOURCE=',     SOURCE
    if DEST   : print 'Looking for DESTINATION=',DEST  

    try:

        command = "fts-transfer-status -s " + os.getenv("FTS_SERVICE")+" -l " + transfer

        lines,errors = runLCG(command,is_pexpect=False)

        if errors:
            print "Couldn't get "+transfer+" statuses"
            return Fail

        # Counters
        n_active   = 0
        n_failed   = 0
        n_finished = 0

        # Ignoring the first line, there are 6 lines of output per transfer formatted as follows
        #         Source:      srm://<smam>
        #         Destination: srm://<eggs>
        #         State:       <blah>
        #         Retries:     <N>
        #         Reason:      <blah>
        #         Duration:    <t>
        #         Staging      <N>
        #Source:      srm://srm-t2k.gridpp.rl.ac.uk/castor/ads.rl.ac.uk/prod/t2k.org/test/Trevor20170707_FTS3_REST_Test/testfile05
        #Destination: srm://t2ksrm.nd280.org/nd280data/Trevor20170707_FTS3_REST_Test/testfile05
        #State:       FINISHED
        #Reason:      
        #Duration:    59
        #Staging:     0
        #Retries:     0

        # (with a blank line in between)
        

        # truncate first line and blank lines
        lines = [ l for l in lines[1:] if l.strip() ]

        # now read 6 lines at a time
        chunk   = 7
        n_reads = 1
        for i in xrange(len(lines)/chunk):

            source   = lines[ i*n_reads*chunk     ].split()[1]
            dest     = lines[ i*n_reads*chunk + 1 ].split()[1]
            state    = lines[ i*n_reads*chunk + 2 ].split()[1]
            print "STATUS!!!!!!!!!!!!!!!!!!!"+SOURCE+" "+source+" "+dest+" "+state+"\n"
            if SOURCE:
                print "inside if for status\n"
                if SOURCE not in source:
                    continue
            print "STATUS2\n"    
            if DEST:
                if DEST not in dest:
                    continue
            print "DEST2\n"        
            print "state "+state
            if state in fts3_active_list   : n_active   += 1
            if state in fts3_failed_list   : n_failed   += 1
            if state in fts3_finished_list : n_finished += 1
            
        ## Print message
        print '%4d active, %4d finished and %4d failed files in : %s' % (n_active,n_finished,n_failed,transfer)              
        return n_active,n_failed,n_finished
    except:
        traceback.print_exc()
        return Fail
        

########################
## The GRID is flaky, timeout commands or wrap them in pexpect
def runLCG(in_command,in_timeout=300, is_pexpect=True):

    lines =[]
    errors=[]

    ## Use pexpect (default)
    if is_pexpect:
        # Use pexpect with 5 min timeout
        tries = 0

        # Temporary log file to contain stdout/stderr redirection
        temp_filename = '.pexpect.'+str(os.getpid())
        # Write temp file to scratch if possible
        if os.getenv("ND280SCRATCH"):
            temp_filename = os.getenv("ND280SCRATCH")+'/'+temp_filename

        # Regex for identifiying errors (can't easily pick up the stderr pipe separately)
        error_regex = '(?i)usage: |(?i)no such|(?i)invalid|(?i)illegal|(?i)error|(?i)failure|(?i)no accessible|'
        error_regex+= '(?i)unauthori[sz]ed|(?i)expire|(?i)exceed|(?i)fatal|(?i)abort|(?i)denied|(?i)no available|(?i)timed out'

        # Try 3 times then give up
        print datetime.now()
        while tries<3:
            print 'Try pexpect '+str(tries)+' of '+in_command+' with '+str(in_timeout)+'s timeout'

            # Spawn process
            child = pexpect.spawn(in_command, timeout=in_timeout)

            # Open temp file
            fout = file(temp_filename,'w+')
            child.logfile_read = fout

            # Attempt the command
            pi = child.expect([pexpect.TIMEOUT, pexpect.EOF, error_regex])
            #print child.before
            #print child.after

            # Read output from temp file stripping carriage returns
            fout.seek(0)
            output = [line.strip() for line in fout.readlines()]
            
            # Close and delete temp file
            fout.close()
            os.remove(temp_filename)
            
            # Close the connection to the spawned process
            try:    child.close()
            except: traceback.print_exc()
    
            # Possible outcomes
            if pi == 0:
                print 'Timeout! ('+str(in_timeout)+'s)'
                tries += 1
                continue
            if pi == 1:
                lines  = output
                errors = []
                break 
            if pi == 2:
                print 'ERROR!'
                print '\n'.join(output)
                errors.append('ERROR!'+repr(output))
                tries += 1
                time.sleep(min(in_timeout,3))
                continue


    ## Don't use pexpect
    else:
        ## Add lcg-* timeouts
        if 'lcg-' in in_command:
            in_command += ' --connect-timeout '    +str(in_timeout)
            in_command += ' --sendreceive-timeout '+str(in_timeout)
            in_command += ' --bdii-timeout '       +str(in_timeout)
            if 'lcg-ls' in in_command or 'lcg-rep' in in_command or 'lcg-cr' in in_command or 'lcg-cp' in in_command:
                in_command += ' --srm-timeout '+str(in_timeout)
                
        # Limit the execution time to 5 min
        # - note this only clocks CPU time so zombie
        # processes will last forever..
        command='ulimit -t '+str(max(300,in_timeout))+'\n'+in_command
        
        ## try the command a few times because failures happen on the GRID
        print datetime.now()
        for ii in range(3):
            print 'Try '+str(ii)+' of '+ in_command+' with '+str(in_timeout)+'s timeout'

            p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
            lines  = p.stdout.readlines()
            errors = p.stderr.readlines()

            if errors:
                print 'ERROR!'
                print '\n'.join(errors)
                time.sleep(min(in_timeout,3))
                continue
            else:
                break
        # Removal of newlines, carriage retruns
        lines  = [l.strip() for l in lines]
        errors = [e.strip() for e in errors]

    return lines,errors

########################
## Return alias given a LFN or SURL
def getAlias(filename):
    """ Command returns the LFN alias of any lfn or surl """
    print 'GetAlias for ' + str(filename)
    command='lcg-la ' + filename
    lines,errors = runLCG(command)
    if not errors and lines:
        return lines[0].replace('\n','').replace('//','/')
    else:
        raise Exception

########################
## Return replicas given an LFN or SURL
def getReps(filename):
    """ Command returns the surl replicas of this file given any lfn or surl """

    print 'GetReps for ' + str(filename)
    reps=[]
    
    command="lcg-lr --vo t2k.org " + filename
    lines,errors = runLCG(command)
    if not errors:
        for l in lines:
            # Get rid of new line and any double // 
            # and then reinstate lost a slash in srm://
            l.replace('\n','').replace('//','/').replace('srm:/','srm://')
            reps.append(l)
        return reps
    else:
        raise Exception

########################
## Return guid given a LFN or SURL
def getGUID(filename):
    """ Command returns the guid of any lfn or surl """
    print 'GetGUID for ' + str(filename)
    command='lcg-lg ' + filename
    lines,errors = runLCG(command)
    if not errors and lines:
        return lines[0].replace('\n','')
    else:
        raise Exception

########################
## Get MyProxy password from environment if defined
def getMyProxyPwd():
    pwd_file = os.getenv("MYPROXY_PWD")
    if pwd_file:
        command = 'cat '+pwd_file

        p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        errors = p.stderr.readlines()

        if not errors:
            lines  = p.stdout.readlines()
            return rmNL(lines[0])
        else:
            return ''
    else:    
        return ''

########################
## Send a single file to the RAL File Transfer Service
def runFTS(original_filename,copy_filename):
    ## Use the FTS service 23-11-10
    command = 'fts-transfer-submit -K -o -s ' + os.getenv("FTS_SERVICE")
    ## comment out for legacy mode
    command+=' -m '+os.getenv("MYPROXY_SERVER")
    ##if getMyProxyPwd():
    ##    command+= ' -p '+getMyProxyPwd()
    ## Implement space token
    srm_b = GetSEFromSRM(copy_filename)
    if se_spacetokens[srm_b]:
        command+=' -t T2KORGDISK' 
    command+= ' ' + original_filename + ' ' + copy_filename
    lines,errors = runLCG(command)
            
    ## Add this transfer to the transfer log
    transfer_dir=os.getenv("ND280TRANSFERS")
    if not transfer_dir:
        transfer_dir = os.getcwd()
    datestring = date.today().isoformat().replace('-','')
    transfer_log = open(transfer_dir + '/transfers.' + datestring + '.log',"a")
    transfer_log.write(rmNL(lines[0]) + ' ' + getAlias(original_filename) + ' ' + copy_filename + '\n')
    transfer_log.close()
    ## print '\n'.join(lines)
    return copy_filename

########################
## Determine number of lines in a file
def FileLineCount(filename):
    count=0
    if os.path.exists(filename):
        for line in open(filename):
            count+=1
        
    return count

## Number of files put in an FTS transfer limit to 200 
## since monitoring pages only display 200 files
## http://lcgwww.gridpp.rl.ac.uk/cgi-bin/fts-mon/fts-mon.pl?q=jobs&p=day&v=t2k.org
NTRANSFERS=200                   
TRANSFER_FILE_LIST=[]
MAX_TRANSFERS_PER_CHANNEL=600


########################
## Send multiple files to the RAL File Transfer Service
def runFTSMulti(srm,original_filename,copy_filename,isLastFile=False,ftsInt=0):
    print 'runFTSMulti: srm='+srm+' orig='+original_filename+' copy='+copy_filename+' isLastFile='+str(isLastFile)+' ftsInt='+str(ftsInt)

    # is this a forced copy?
    isForcedCopy=0
    
    ## Environment
    transfer_dir=os.getenv("ND280TRANSFERS")
    if not transfer_dir:
        transfer_dir = os.getcwd()
    print 'Transfer directory: '+transfer_dir    
    datestring = date.today().isoformat().replace('-','')
    print 'Datestamp:'+datestring
    
    ## Write SRM pairs to filelist
    if original_filename != copy_filename:
        srm_a = GetSEFromSRM(original_filename)
        srm_b = GetSEFromSRM(copy_filename)

        ## Make sure source and destination exist
        if not len(srm_a):
            print "Source missing!"
            raise Exception
        if not len(srm_b): 	 
            print "Destination missing!"
            raise Exception
        if not 'srm' in original_filename: 	 
            print original_filename + ' not a valid SURL!'
            raise Exception
        if not 'srm' in copy_filename: 	 
            print copy_filename + ' not a valid SURL!' 	 
            raise Exception
        
        listname=transfer_dir+'/transfer.'+srm_a+'-'+srm_b
        if ftsInt:
            listname+='.'+str(ftsInt)
        listname+='.txt'
        
        print 'Accessing channel:'+listname
            
        ## Add this transfer file to the list if not present
        if (not listname in TRANSFER_FILE_LIST):
            TRANSFER_FILE_LIST.append(listname)
            print 'Added '+listname+' to transfer file list.'

        try:
            filelist = open(listname,"a")
            filelist.write(original_filename+' '+copy_filename+'\n')
            filelist.close()
        except:
            print "Couldn't write to "+listname

    else:
        print 'Trying to overwrite '+original_filename+' with itself!:'+copy_filename
        if not isLastFile:
            raise Exception
        else:
            print 'Forcing copy to invoke FTS, resetting SRMs...'
            isForcedCopy=1
            srm_a = ''
            srm_b = ''

    ## Submit file for each sourcea dn destination, keep track of submissions and remove from
    ## TRANSFER_FILE_LIST accordingly
    submittedList = []

    print 'Transfer File List:'
    print repr(TRANSFER_FILE_LIST)

    for transfer in TRANSFER_FILE_LIST:
        
        ## Submit after NTRANSFERS files in list or file is last in directory
        ## and not the only to be transferred
        nlines = FileLineCount(transfer)
        if nlines>=NTRANSFERS or (isLastFile and nlines>1) or isForcedCopy:
            print 'Using the FTS service'
            print str(nlines)+' files to transfer in this job'
            
            if isLastFile:
                print original_filename+' is the last file in this directory'            

                if isForcedCopy:
                    ## Derive SRMs from transfer in case of forced copy
                    if not srm_a and not srm_b:
                        print 'Deriving SRMs from '+transfer
                        ## Get srm_a:
                        for srm in se_roots.keys():
                            if 'transfer.'+srm in transfer:
                                srm_a = srm
                                break
                        ## Get srm_b:
                        for srm in se_roots.keys():
                            if 'transfer.'+srm_a+'-'+srm in transfer:
                                srm_b = srm
                                break
                print 'SRMs: ',srm_a,srm_b

            ## Check SRM info exists
            if srm_a not in se_roots.keys()   or srm_b not in se_roots.keys():
                print 'Could not identify SEs: '+srm_a+' '+srm_b
                raise Exception

            ## Don't submit any more transfers if already 
            ## MAX_TRANSFERS_PER_CHANNEL on the queue, unless these are coming out of kek
            if not 'kek.jp' in srm_a:
                print 'Checking FTS transfers between %s and %s' % (srm_a,srm_b)

                while 1:
                    n_active           = 0
                    transfers,statuses = GetActiveTransferList(srm_a,srm_b)

                    for trans in transfers:
                        n_active += GetTransferStatus(trans,srm_a,srm_b)[0]

                    ## Okay to submit?
                    if n_active <= MAX_TRANSFERS_PER_CHANNEL:
                        print 'Okay to submit transfers!'
                        break

                    ## If not, sleep
                    time.sleep(60)

            ## Now, submit the transfer
            command = 'fts-transfer-submit --verbose -K -o -s ' + os.getenv("FTS_SERVICE")
            ## comment out for legacy mode
            #command+=' -m '+os.getenv("MYPROXY_SERVER")
            ## Implement space token
            if se_spacetokens[srm_b]:
                command+=' -t T2KORGDISK' 
            command+=' -f '+transfer
            #print 'runFTSMulti: '+command
            lines,errors = runLCG(command)

            ## if this is a transfer out of kek, increase priority
            if lines and not errors:
                transfer_id = lines[0]
                priority    = str(5)
                #                if 'kek.jp' in srm_a:
                #                    command = 'glite-transfer-setpriority -s ' + os.getenv("FTS_SERVICE") + transfer_id + ' ' + priority
                #                    lines,errors = runLCG(command)

            ## Write the transfer log - just FTS ID
            transfer_log = open(transfer_dir + '/transfers.' + datestring + '.log',"a")
            transfer_log.write(lines[0]+'\n')
            transfer_log.close()

            ## Now remove this transfer
            print 'Removing %s' % (transfer)
            #if os.path.exists(transfer):
            os.remove(transfer)
            submittedList.append(transfer)

        elif isLastFile and nlines==1:
            print 'No new files to transfer!'
            print 'Removing %s' % (transfer)
            #if os.path.exists(transfer):
            os.remove(transfer)
            submittedList.append(transfer)
        else:
            # print 'Not last file and not exceeded '+str(NTRANSFERS)+' transfers on '+channel
            pass

    ## end of loop over TRANSFER_FILE_LIST

    for submitted in submittedList:
        TRANSFER_FILE_LIST.remove(submitted)

    print 'runFTSMulti exited cleanly'
    return copy_filename

########################
## Get the path to the current raw data directory
def GetCurrentRawDataPath(subdet='ND280',det='ND280'):
    """
    Get the path to the current raw data directory:
    /nd280/raw/ND280/ND280/0000*000_0000*999

    Currently just searches for folder with highest run number that is
    not empty
    """
    dirs            = []
    errors          = []
    try:
        raw_data_folder = '/grid/t2k.org/nd280/raw/'+det+'/'+subdet
        command = "lfc-ls "+raw_data_folder
        dirs,errors = runLCG(command)
        if errors: raise Exception

        ## truncate any folders that are not of the 0000*000_0000*999 format from the list
        dirs = [dir for dir in dirs if '999' in dir]

        ## Find directory with highest run number and non zero content
        for dir in reversed(dirs):
            command = "lfc-ls "+raw_data_folder+"/"+dir
            files,errors = runLCG(command)
            if errors         : raise Exception
            if not len(files) : continue
            else              : return (raw_data_folder+'/'+dir).replace('/grid/t2k.org','').strip()
            
    except:
        print 'Unable to get current raw data path for '+str(det)+'/'+str(det)
        print '\n'.join(errors)
        return ''

########################
## Get the current raw data folder
def GetCurrentRawDataFolder(subdet='ND280',det='ND280'):
    """
    returns string of form 0000*000_0000*999
    """
    try:
        path = GetCurrentRawDataPath(subdet,det).split('/')
        if not path : raise Exception
        else        : return rmNL(path[len(path)-1])
    except:
        print 'Unable to get current raw data folder.'
        return ''


########################
## How many raw data files are at KEK in the given directory?
def GetNRawKEKFiles(lfc_dir):
    """
    Query the TRIUMF MYSQL database for the number of raw data files on the KEK
    HPSS corresponding to the specified LFC raw data directory
    e.g. lfc_dir='lfn:/grid/t2k.org/nd280/raw/ND280/ND280/00000000_00000999/'
    """
    ## mysql will fail if directory has terminating slash (/) or any double
    ## slashes (//) in path
    try:
        command = 'mysql -u t2kgsc_reader --password=rdneutgsc -h t2kgscdb.triumf.ca -e \"select * from t2kgscND280.DAQ_FILE_ARCHIVE where DS_directory like \'%'+lfc_dir.split('raw')[1].rstrip('/').replace('//','/')+'\'\" | grep nd280 | wc -l'
        print command

        p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        lines  = p.stdout.readlines()
        errors = p.stderr.readlines()

        if not errors:
            return int(lines[0])
        else:
            return 0
    except:
        traceback.print_exc()
        return 0
    
########################
## How many good runs in specified LFC directory?
def GetNGoodRuns(lfc_dir):
    """
    Query $ND280COMPUTINGROOT/data_scripts/GoodRuns.list for number of 
    good run files in specified LFC directory
    """
    command = 'grep '+lfc_dir+' $ND280COMPUTINGROOT/data_scripts/GoodRuns.list | wc -l'
    print command
    p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
    lines  = p.stdout.readlines()
    errors = p.stderr.readlines()
    
    if not errors:
        return int(lines[0])
    else:
        return 0

########################
## Return a standardised SURL, given an SRM
def DIRSURL(lfn,srm):
    """
    Return a standardised surl, given an srm.
    Just returns the input filename if surl originally but transforms 
    lfn into surl. Raises error if not gridfile.
    """
    ## Clear out any double //
    lfn.replace('//','/')
    dirsplit=lfn.split("/")

    if 'lfn:' in lfn:
        i=dirsplit.index("t2k.org") ## Should always be 1
        surl=se_roots[srm].rstrip('/')
        dirparts=dirsplit[i+2:]     ##start from nd280 version

        if 'contrib' in lfn: ## Added for users saving to their contrib directory - ben 17/10/13
            surl=surl.replace('/nd280data','') ##  Need to remove the preceeding /nd280data/ - only works for t2ksrm
            surl=surl.replace('/nd280','') ##  Need to remove the preceeding /nd280/ - all other se_roots
            dirparts=dirsplit[i+1:] ## keep the contrib part of the directory

        for fp in dirparts:
            surl+= "/" + fp
        return surl
    else:
        raise self.Error('Not an LFN')
    return 0


########################
## Get ND280 software directory
def GetT2KSoftDir():
    t2ksoftdir = os.getenv("VO_T2K_ORG_SW_DIR")
    if not t2ksoftdir:
        t2ksoftdir = os.getenv("VO_T2K_SW_DIR")
    if not t2ksoftdir:
        return ""
    return t2ksoftdir

########################
## Get the default SE to store output on, defaults to RAL
def GetDefaultSE():
    """ Get the default SE to store output on, defaults to RAL. Also checks if the default SE is int he list of se_roots """
    default_se=os.getenv("VO_T2K_ORG_DEFAULT_SE")
    if not default_se or not default_se in se_roots:
        default_se = os.getenv("VO_T2K_DEFAULT_SE")
    if not default_se or not default_se in se_roots:
        return "srm-t2k.gridpp.rl.ac.uk"
    return default_se
    

########################
## Is VOMS proxy valid?
def CheckVomsProxy():
    print 'CheckVomsProxy'

    # initialize
    timeleft = 0 
    
    command= 'voms-proxy-info -timeleft'
    lines,errors = runLCG(command)

    if lines:
        print lines[0]+' seconds remaining'
        if lines[0].isdigit():
            timeleft = int(lines[0])
    
    if errors or timeleft<120:
        
        ## Wait a few minutes for renewal
        print 'Waiting a few minutes for proxy renewal'
        time.sleep(360)
        
        ## Try again
        lines,errors = runLCG(command)
        timeleft = 0 

        if lines:
            print lines[0]+' seconds remaining'
            if lines[0].isdigit():
                timeleft = int(lines[0])
                
        ## If still no proxy return 1
        if errors:
            print '\n'.join(errors)
        if timeleft<120:
            return 1

    ## Proxy is valid
    return 0

########################
## Set important environment variables - these are also setup (for the shell, but not subprocesses [e.g on a node]) by nd280Computing/setup.sh
## Need to consolidate this for remote shells and subprocesses.
def SetGridEnv():
    print 'SetGridEnv()'
    ## LFC environment variables
    if not os.getenv("LFC_HOST") or os.getenv("LFC_HOST") != "lfc.gridpp.rl.ac.uk":
        os.environ["LFC_HOST"]="lfc.gridpp.rl.ac.uk"

    ## Explicitly specify LFC catalogue instead of RLS 
    if not os.getenv("LCG_CATALOG_TYPE") or os.getenv("LCG_CATALOG_TYPE") != "lfc":
        os.environ["LCG_CATALOG_TYPE"]="lfc"

    ## Set LFC Home
    if not os.getenv("LFC_HOME") or os.getenv("LFC_HOME") != "/grid/t2k.org/nd280":
        os.environ["LFC_HOME"]="/grid/t2k.org/nd280"
    
    ## Use GRIDFTP 2
    if not os.getenv("GLOBUS_FTP_CLIENT_GRIDFTP2") or os.getenv("GLOBUS_FTP_CLIENT_GRIDFTP2") != 'true':
        os.environ["GLOBUS_FTP_CLIENT_GRIDFTP2"]='true'
    
    ## BDII
    if not os.getenv("LCG_GFAL_INFOSYS") or os.getenv("LCG_GFAL_INFOSYS") != 'lcg-bdii.gridpp.ac.uk:2170':
        os.environ["LCG_GFAL_INFOSYS"]='lcg-bdii.gridpp.ac.uk:2170'

    ## MYPROXY SERVER
    if not os.getenv("MYPROXY_SERVER"):
        os.environ["MYPROXY_SERVER"]='myproxy.gridpp.rl.ac.uk'
        
    return 0

## Set the env when this module is imported, if it isn't set
for var in ['LFC_HOST','LCG_CATALOG_TYPE','LFC_HOME']:
    if not os.getenv(var):
        SetGridEnv()
        break

########################
## Removes those annoying newlines from a string
def rmNL(inStr):
    return inStr.replace("\n","")

########################
## Pads out a run number with preceeding 0's
def PadOutRun(run):
    run=str(run)
    while len(run) < 8:
        run = "0" + run
    return run

########################
## Pads out a subrun number with preceeding 0's
def PadOutSubrun(subrun):
    subrun=str(subrun)
    while len(subrun) < 4:
        subrun = "0" + subrun
    return subrun

########################
## Pads out a subrun number with preceeding 0's
def PadOutVersion(ver):
    ver=str(ver)
    while len(ver) < 3:
        ver = "0" + ver
    return ver

########################
## Calculate the run range directory for a given run number, string or integer
def RunRange(run):
    runnumber = 1000*int(int(run)/1000)
    runend = PadOutRun(str(runnumber + 999))
    runnumber = PadOutRun(str(runnumber))

    return runnumber + "_" + runend


########################
## Strip the SE from an SRM
def GetSEFromSRM(srm):
    return srm.replace('//','/').replace('srm:/','').split('/')[0]
    

########################
## MySQL query to return list of raw files produced in the last N days
def GetNDaysRawFileList(nDays=10,subDet='nd280'):

    command = 'mysql -s -u t2kgsc_reader --password=rdneutgsc -h t2kgscdb.triumf.ca -e "select DS_Directory,File_Name from t2kgscND280.DAQ_FILE_ARCHIVE where Archive_Date >= curdate() - interval '+str(nDays)+' day && File_Name like \'%'+subDet+'_%\'"'
    lines,errors = runLCG(command,is_pexpect=False)
    
    return [ '/'.join(l.split()).strip().replace('/gpfs/fs03/t2k/nd280/barr/archive','lfn:'+os.getenv('LFC_HOME')+'/raw') for l in lines ]


########################
## Wrapper function for ND280File.CopyLocal()
def LocalCopyLFNList(fileList=[],localRoot='',defaultSE='srm-t2k.gridpp.rl.ac.uk'):
    
    # maintain list of failed copies
    listOfFailures = []
            
    # copy files locally
    for fileName in fileList:

        # extract lfc directory from file name (may be different if a directory boundary is crossed)
        lfcDir = os.path.dirname(fileName)

        # define path to local destination which preserves LFC structure
        localDir = lfcDir.replace('lfn:'+os.getenv('LFC_HOME'),localRoot)
    
        # create destination directory if necessary
        if not os.path.exists(localDir):
            print 'Making local directory '+localDir
            os.makedirs(localDir)

            # balk if directory couldn't be created
            if not os.path.exists(localDir):
                sys.exit('Unable to create '+localDir)

        # the local path to this file
        localPath = localDir+'/'+os.path.basename(fileName)

        # check it doesn't already exist
        if not os.path.exists(localPath):

            # not all files on archiver, will be uploaded to grid yet
            try:
                f = ND280File(fileName)
                f.CopyLocal(localDir,defaultSE)
            except:
                traceback.print_exc()
                listOfFailures.append(fileName)
        else:
            print localPath+' exists!'
                
    if len(listOfFailures):
        print '%d failures:' % (len(listOfFailures))
        for fail in listOfFailures: print fail


    return

########################
## Given a logical path to a log file, query it for the *.root files created by the job and determine
## if they exist in the LFC
def LogFileConsistencyCheck(logFileLFN=''):
    
    logFileName = logFileLFN.split('/')[-1]

    # does a local copy exist?
    if not os.path.exists(logFileName):
        f = ND280File(logFileLFN)
        f.CopyLocal(os.getcwd())

    # read the lines
    lines = [ l.strip() for l in open(logFileName,'r').readlines() ]

    # add root file names to a list
    rootFiles = []

    # look for lines containing root file names
    for l in lines:
        if '.root' in l:

            # split ino words
            words = l.split()

            # find root file name and truncate directory paths where appropriate
            for w in words:
                if '.root' in w:
                    rootFiles.append(w.split('/')[-1])


    # uniquify list of root files
    rootFiles = list(set(rootFiles))

    # keep a list of missing files
    missingFiles = []

    # check that all files exist
    for r in rootFiles[:]:

        # determine processing stage
        stage = r.split('_')[5]
        
        # try and make a file object
        try:
            # logical path to root file
            rootFileLFN = logFileLFN.replace('logf/'+logFileName,'')+stage+'/'+r
            f = ND280File(rootFileLFN)
        except:
            # if file doesn't exist, remove from list of root files and add to list of missing
            rootFiles.remove(r)
            missingFiles.append(r)

    # print list of root files and missing files
    for r in rootFiles:
        print 'File present:',r
    for m in missingFiles:
        print 'File missing:',m

########################
## Get a random seed from has of run + subrun + stage, nBits
def GetRandomSeed(run='',subrun='',stage='', hexbits=8):
    run    = str(run)
    subrun = str(subrun)
    stage  = str(stage)
    h = sha1(run+subrun+stage)
    # 32 bit unsigned integer -> 8 hexbits : max = 0xFFFFFFFF = 2^32-1 = 4294967295 : nd280Control
    # 32 bit signed   integer -> 7 hexbits : max = 0xFFFFFFF  = 2^31-1 = 268435455  : nd280MC, neut
    bits = int(h.hexdigest()[:hexbits],16)
    print 'Random seed for %s is %d' % (run+'-'+subrun+'-'+stage,bits)
    return bits


########################
## Create a config file name given an input
def GetConfigNameFromInput(inputPath=''):
    return os.path.splitext(os.path.basename(inputPath))[0]+'.cfg'


########################
## does exactly what it says on the tin
def FindAndReplaceStringInFile(filepath='',findstring='',replacestring=''):
    
    fin      = open(filepath,'rb')
    instring = fin.read()
    fin.close()

    if findstring in instring:
        print 'replacing %s with %s in %s ' % (findstring,replacestring,filepath)
    
    outstring = instring.replace(bytes(findstring),bytes(replacestring))
    fout      = open(filepath,'wb')
    fout.write(outstring)
    fout.close()

    return


########################
## does exactly what it says on the tin
def GetSubRunFromFlukaFileName(flukaFileName=''):
    # iseq may or may not be in the file name, this function assumes that the sequence number is the only numeric field
    iseq    = [ x for x in re.split('[._]',flukaFileName) if x.lstrip('iseq').isdigit() ][0]
    return int(iseq)



#############################################################################################################
########### ND280File Class
#############################################################################################################

class ND280File:

    """ A class that contains useful file functions """
    def __init__(self, fn, check=True):
        """
        Initialise the ND280File object.
        Characterises the file and performs check to test if the file exists in the location specified.
        Only works with LFC and local files.
        """
        ## check argument allows for disabling of proxy and env check for speed
        ## it is set to false for ND280Dir.ND280File since the ND280Dir
        ## constructor does this check too
        if check:
            if CheckVomsProxy():
                raise self.Error('No valid proxy')
            SetGridEnv()

        ## Get rid of any new lines and trailing slashes
        fn           =fn.strip().rstrip('/') 
        self.filename=fn.split('/')[len(fn.split('/'))-1]
        self.path=    fn.replace(self.filename,'')

        self.turl='' ## transfer url used by some file systems
        
        ## Get the replicas of this file
        self.reps=[]
        self.alias=''
        self.guid=''
        self.size=0
        self.gridfile=''
        self.is_a_dir=False
        try:
            if 'lfn:' in fn or 'srm:' in fn or 'guid:' in fn:
                self.reps =getReps (fn)
                self.alias=getAlias(fn)
                self.guid =getGUID (fn)

                ## Get the file size from the (formatted) LFC long listing
                try:
                    lines,errors = runLCG('lfc-ls -ld '+self.alias.replace('lfn:',''))
                    if lines:
                        self.size     = int(lines[0][27:51])
                        self.is_a_dir = 'd' in lines[0][0]
                except:
                    print "Couldn't establish filesize"

                ## Set up relative paths and filename
                self.path=self.alias.replace('lfn:/grid/','').replace(self.filename,'')
                self.gridfile='l'


            else:
                ## This file is not registered on the GRID, is it local?
                command = 'ls ' + fn
                rtc = os.system(command)
                if rtc:
                    raise self.Error('This file is not registered on the LFC and does not exist on the local system ' + fn)
                self.gridfile=''
        except:
            raise self.Error('Unable to establish file type of '+fn)
            
        ## File type, p=processed, r=raw, m=MC, o=other, n=none
        if 'oa_nd_' in self.filename:
            self.filetype='p'
        elif 'oa_nt_' in self.filename or 'oa_gn_' in self.filename:
            self.filetype='m'
        elif 'nd280_' in self.filename:
            self.filetype='r'
        elif 'dsecal_' in self.filename:
            ## CERN testbeam data
            self.filetype='c'
        else:
            self.filetype='o'


        
    def __del__(self):
        """ Clean up after the object. If you have requested a turl then set file status to done. """
        ## If you have a turl set the file state to done.
        if self.turl:
            command='lcg-sd ' + self.turl[0] + ' ' + self.turl[2].replace('\n','') + ' 0'
            print command
            rtc=os.system(command)
            if rtc:
                raise self.Error('Could not set done file turl ' + self.turl[0] + ' located at ' + self.turl[1])
    
    ### Internal Error class for raising errors
    class Error(Exception):
        pass

    ########################################################################################################################
    ######################## Functions to parse certain information from the filename ######################################
    ########################################################################################################################

    ## Returns the 5 character file hash. Works on any processed filename as it just uses the final '/' split as a file name.
    ## E.g. GetFileHash(/grid/t2k.org/nd280/mcp1/genie/2010-02-water/Magnet/beam/numc/oa_gn_beam_91000098-0093_dxf44iaxt3e7_numc_000_mcp1geniemagnet.root)
    ## returns dxf44
    def GetFileHash(self):
        """ Get the unique file hash of processed file, throws error if not a processed file  """
        if not self.filetype=='p' and not self.filetype=='m':
            raise self.Error('This is not a processed or MC file, cannot get file hash. File type is ', self.filetype)
        fn_spl=self.filename.split('_')
        file_hash=fn_spl[4][0:4]
        return file_hash

    ## return the stage of the processing
    def GetStage(self):
        """ Get the stage of processed file, throws error if not a processed file  """
        if not self.filetype=='p' and not self.filetype=='m':
            raise self.Error('This is not a processed or MC file, cannot get stage of processing.')
        fn_spl=self.filename.split('_')
        return fn_spl[5]
    ## Return the Version
    def GetVersion(self):
        """ Get the version of processed file, throws error if not a processed file  """
        if not self.filetype=='p' and not self.filetype=='m':
            raise self.Error('This is not a processed or MC file, cannot get version.')
        fn_spl=self.filename.split('_')
        return fn_spl[6]
    ## Return the file comment
    def GetComment(self):
        """ Get the comment of processed file, throws error if not a processed file  """
        if not self.filetype=='p' and not self.filetype=='m':
            raise self.Error('This is not a processed or MC file, cannot get comment.')
        fn_spl=self.filename.split('_')
        return fn_spl[7].split('.')[0]
    ########################
    ## Calculate the run range directory from a filename
    def GetRunRange(self):
        """ Gets the range in which this run lies: 00001000-00001999, 00002000-00002999 ... etc """
        runno=int(self.GetRunNumber())
                          
        return RunRange(runno)

    ########################
    ## Get run and subrun No. of data files
    ## nd280_00003998_0000.daq.mid.gz
    def GetRunNumber(self):
        """ Get the run number by parsing the file name """
        fn_spl=self.filename.split(".")[0]
        fn_spl=fn_spl.split("_")
        if self.filetype=='r':
            return fn_spl[1]
        elif self.filetype=='p' or self.filetype=='m':
            rn=fn_spl[3]
            rn=rn.split("-")
            return rn[0]
        elif self.filetype=='c':
            return fn_spl[1]
        else:
            return ''

    def GetSubRunNumber(self):
        """ Get the sub run number by parsing the file name """
        fn_spl=self.filename.split(".")[0]
        fn_spl=fn_spl.split("_")
        if self.filetype=='r':
            return fn_spl[2]
        elif self.filetype=='p' or self.filetype=='m':
            rn=fn_spl[3]
            rn=rn.split("-")
            return rn[1]
        elif self.filetype=='c':
            return fn_spl[2]
        else:
            return ''

    ########################################################################################################################
    ######################## Methods for grid resident files ###############################################################
    ########################################################################################################################

    def LFN(self):
        """
        Return a standardised Logical File Name.
        Just returns the input filename if LFN originally but transforms srm into lfn. Raises error if not gridfile.
        """
        
        if self.gridfile:
            return self.alias
        else:
            raise self.Error('Local file')
        return 0

    def SURL(self,srm):
        """
        Return a standardised surl, given an srm.
        Transforms lfn into surl. Raises error if not gridfile.
        also returns if the file is on the srm
        return = surl,onSRM
        """
        ## Loop over replicas and return if the surl and that it exists as a replica
        for r in self.reps:
            if srm in r:
                return r,1

        pathsplit=self.alias.split("/")
        
        if self.gridfile:
            i=pathsplit.index("t2k.org") ## Should always be 2 0=lfn:, 1=grid, 2=t2k.org
            print 'SE_ROOTS[srm] '+se_roots[srm]+'\n'
            surl=se_roots[srm].rstrip('/')
            print 'SURL1 '+surl+'\n'
            if 'contrib' in self.alias: ## Added for users saving to their contrib directory - ben 17/10/13
                surl=surl.replace('/nd280data','') ##  Need to remove the preceeding /nd280data/ - only works for t2ksrm
                surl=surl.replace('/nd280','') ##  Need to remove the preceeding /nd280/ - all other se_roots
            #if '.ic.ac.uk' in srm:
            #    i+=1
            #    surl+='/t2k'
            #elif 't2ksrm.nd280.org' in srm:
            #    i+=2
            #    surl+='/nd280data'
            print 'SURL2 '+surl+'\n'
            fileparts=pathsplit[i+2:] #Start from nd280 version

            for fp in fileparts:
                surl+= "/" +fp
            print 'SURL3 '+surl+'\n'
            if self.filename not in surl:
                surl+=self.filename
            print 'SURL4 '+surl+'\n'
            return surl, self.OnSRM(srm)
        else:
            ##raise self.Error('Not an LFN')
            return 0,0

    #### Is a GRID file on SRM
    def OnSRM(self,srm):
        """ 
        Check to see if the current file exists on a particular srm.
        If it does then return the full filename, else throw and error.
        On LFC is a moot point as all ND280Files have to be registered
        """

        if not self.gridfile:
            return ''

        srmfname=""
        for r in self.reps:
            if srm in r:
                srmfname=r

        return srmfname

    ### Get a file hash (Currently only supported on the file system at QMUL)
    def GetTurl(self):
        """ Get a file transfer url using the file protocol, currently only supported on storm systems I.e. QMUL se03 """
        print 'GetTurl'
        srmname=''
        site_name=''

        site_name=os.getenv("SITE_NAME")
##         if not site_name:
##             site_name=os.getenv("HOSTNAME")
        if not site_name:
            raise self.Error('Cannot get the env variable SITE_NAME: On a GRID node? No=Don\'t Worry, yes=WTF')

        print 'site name ' + site_name
        if self.gridfile:
            if "QMUL" in site_name:
                ## if we are at QMUL then get the turl of the local copy of the file
                for r in self.reps:
                    if 'qmul.ac.uk' in r:
                        srmname=r
                        
                print 'srm name ' + srmname
                if srmname:
                    command="lcg-gt " + srmname + " file"
                    lines,errors = runLCG(command)
                    if errors:
                        raise self.Error('Could not get file turl',errors)
                    file_turl=lines[0].replace('\n','')
                    file_turl=file_turl[7:] #remove the preceeding file://

                    self.turl=[srmname] + lines
                    print 'TURL: ' + file_turl
                    return file_turl
                else:
                    raise self.Error('Could not find file registered at QMUL')
            else:
                raise self.Error('Can only get turl at qmul')
        else:
            raise self.Error('Only use the GetTurl method with an LFN')

    def GetRepSURL(self,srm=''):
        print 'GetRepSURL(srm='+srm+')'
        """ Get the surl for this file from replica list.
        Priority is as follows:
        1. srm passed as argument
        2. RAL
        3. IN2P3 or TRIUMF
        4. The first listed replica.
        """
        original_filename=''
        if self.path:
            original_filename=self.path + '/'
        original_filename+= self.filename
        ## Get surl from replica list

        ## Prioritise the users choice of srm
        if srm:
            for r in self.reps:
                if srm in r:
                    return r
        
        ## Prioritise RAL
        for r in self.reps:
            if 'srm-t2k.gridpp.rl.ac.uk' in r:
                return r
        ## Then TRIUMF and IN2P3 equally
        for r in self.reps:
            if 't2ksrm.nd280.org' in r:
                return r
            elif 'in2p3.fr' in r:
                return r
            elif 'qmul' in r:
                return r
        ## If none of the above then just choose the first
        if self.reps:
            return self.reps[0]
        ## Or return a blank
        else:
            return ''

    def CopySRM(self,srm,use_fts=0,isLastFile=False,ftsInt=0):
        print 'CopySRM()'

        original_filename=self.GetRepSURL()
        
        ## remove errant '//' ignoring the first 10 characters
        original_filename = original_filename[:10] + original_filename[10:].replace('//','/')
       
        print 'Original filename '+original_filename

        if not self.gridfile:
            raise self.Error('Trying to copy local file to srm, tut tut tut!')

        if self.is_a_dir:
            raise self.Error('Cannot copy a directory!')

        ## If the file is already on the srm just return the surl unless
        ## using FTS and this is last file.
        elif srm in original_filename and (not isLastFile) and use_fts:
            print 'Already on srm ' + original_filename
            return original_filename
        
        copy_filename,on_srm=self.SURL(srm)
        print 'Copy filename ' + copy_filename
        if (on_srm and not use_fts) or (on_srm and use_fts and not isLastFile):
            print 'Already on srm ' + copy_filename
            return copy_filename
        
        if use_fts:
            ## first if original file is at RAL, make sure it is staged on disk,
            ## otherwise FTS will timeout
            if 'srm-t2k.gridpp.rl.ac.uk' in original_filename:
                lines,errors = runLCG('lcg-ls -l '+original_filename)
                if errors:
                    raise self.Error('Could not determine staging of '+original_filename)
                else:
                    if not 'ONLINE' in lines[0].split()[5]:
                        runLCG('lcg-bringonline '+original_filename, in_timeout=7200,is_pexpect=False)
            ## Use the FTS service 23-11-10
            return runFTSMulti(srm,original_filename,copy_filename,isLastFile,ftsInt)
        else:            
            command='lcg-rep -v -n 3 '
            if se_spacetokens[srm]:
                command+=' -S T2KORGDISK'
            command += ' -d ' + copy_filename + ' ' + self.alias
            lines,errors = runLCG(command,in_timeout=600)
            if errors:
                print '\n'.join(errors)
                raise self.Error('Could not replicate the file ' + self.alias + ' on the SRM ' + srm + '\n', errors)
            else:
                print '\n'.join(lines)
                return copy_filename

    def CopyLocal(self,dir,srm=''):

        original_filename=self.GetRepSURL(srm)
        copy_filename=dir + '/' + self.filename

        print 'CopyLocal(%s)' % (copy_filename)

        if os.path.exists(copy_filename):
            print 'File exists'
            return copy_filename

        if 'srm-t2k.gridpp.rl.ac.uk' in original_filename:
            lines,errors = runLCG('lcg-ls -l '+original_filename)
            if errors:
                raise self.Error('Could not determine staging of '+original_filename)
            else:
                if not 'ONLINE' in lines[0].split()[5]:
                    lines,errors = runLCG('lcg-bringonline '+original_filename,in_timeout=3600,is_pexpect=False)
                    if errors:
                        print '\n'.join(errors)
                        raise self.Error('lcg-bringonline of '+original_filename+' threw an error')
                    if lines:
                        if 'lcg-bringonline: Success' in lines[0]:
                            print lines[0]
                    else:   
                        lines,errors = runLCG('lcg-ls -l '+original_filename)
                        if not 'ONLINE' in lines[0].split()[5]:
                            raise self.Error('lcg-bringonline of '+original_filename+' did not bring file online')
  
        command='lcg-cp ' + original_filename + ' ' + copy_filename
        lines,errors = runLCG(command,in_timeout=3600,is_pexpect=False) ### timeouts added by hand when not using pexpect
        if errors:
            raise self.Error('Could not copy ' + original_filename + ' to the local directory ' + copy_filename + '\n', errors)
        print '\n'.join(lines)

        ### 6A verification control sample names break nd280Control - rename them
        ### refer to http://www.hep.lancs.ac.uk/nd280Doc/stable/invariant/nd280Control/fileNaming.html
        if self.filename.startswith('oa_') and '_ctl-' in self.filename[:15]:
            # first remove '-' instances from 3rd (ppp) field 
            ppp         = self.filename.split('_')[2]
            newfilename = self.filename.replace(ppp,ppp.replace('-',''))
            # now move second run_subrun instance to comment field
            nnn         ='-'.join(self.filename.split('_')[3].split('-')[2:4])
            newfilename = newfilename.replace('-'+nnn,'')
            newfilename = newfilename.replace('.root',nnn+'.root')
            newfilename = dir +'/' + newfilename
            
            print 'renaming '+copy_filename+' to '+newfilename
            os.rename(copy_filename,newfilename)
            return newfilename
        
        return copy_filename

    ########################################################################################################################
    ######################## Methods for gridlocally resident files ########################################################
    ########################################################################################################################

    def Register(self,lfn='',srm='srm-t2k.gridpp.rl.ac.uk', timeout=300):
        """
        For local files: 
             first copy to grid.
             lfn=the LFC directory wished for the file
             srm=the srm to copy to, default is the RAL srm
        For grid files:
             lfn=the files own alias
             srm=the SURL to register, or the SRM on which to register
        """
        
        ## Local files, lcg-cr
        if not self.gridfile:

            ## Ensure lfn begins with an 'lfn:/' prefix
            if not lfn.startswith('lfn:') : lfn = 'lfn:' + lfn

            ## Ensure lfn (here the LFC destination directory) ends with a slash
            if not lfn.endswith('/') : lfn += '/'

            dest_file = DIRSURL(lfn,srm) + '/' + self.filename
                    
            ## Remove any errant '//' ignoring the first 10 characters
            dest_file = dest_file[:10] + dest_file[10:].replace('//','/')

            ## If we are here then the file doesn't exist on the desination srm so we copy and register:
            command ='lcg-cr -v -v'
            if se_spacetokens[srm]:
                command+=' -s T2KORGDISK'
            command+=' -d ' + dest_file + ' -l ' + lfn + self.filename + ' file:' + self.path + self.filename
            lines,errors = runLCG(command,in_timeout=timeout)
            
            ## Check for existence of replica:
            command = 'lcg-ls ' + dest_file
            lines,errors = runLCG(command)
            if errors:
                ## Last ditch, try replicating elsewhere
                ## Not appropriate to copy data indiscriminately to T2s...
                ## Only try RAL and QMUL (lots of disk) instead:
                for try_srm in ['srm-t2k.gridpp.rl.ac.uk','se03.esc.qmul.ac.uk']:

                    dest_file = DIRSURL(lfn,try_srm) + '/' + self.filename
                    command ='lcg-cr'
                    if se_spacetokens[try_srm]:
                        command+=' -s T2KORGDISK'
                    command +=' -d ' + dest_file + ' -l ' + lfn + self.filename + ' file:' + self.path + self.filename
                    lines,errors = runLCG(command,in_timeout=timeout)

                    ## Check for existence of replica:
                    command = 'lfc-ls -l ' + lfn.replace('lfn:','') + self.filename 
                    lines,errors = runLCG(command)
                    if not errors:
                        return lfn + self.filename
                
                raise self.Error('Error copying local file to the GRID\n',errors)
            else:
                return lfn + self.filename

        # this is a grid file
        else:
            if 'srm:/' in srm:
                dest_file = srm
            else:
                dest_file, on_srm = self.SURL(srm)
                
            command= 'lcg-rf --vo t2k.org -g ' + self.guid + ' ' + dest_file
            lines,errors = runLCG(command)
            
            if errors:
                print '\n'.join(errors)
                raise self.Error('Unable to register ' +self.filename)
            else:
                print "\n".join(lines)
                return self.filename
            

#############################################################################################################
########### ND280Dir Class
#############################################################################################################

class ND280Dir:

    """ 
    A class that allows one to do useful things with local and lfc directories.
    
    """

    ########################
    ## Initialisation, performs checks on the input and sets up the lists to be used by further methods.
    ## Added skipFailures option, to permit construction of ND280Dir object with ommission of failed
    ## ND280Files - use with caution.
    def __init__(self, dir, skipFailures=False, ls_timeout=300):
        """ Initialisation of ND280Dir object

        self.dir: str The path of this directory
        self.dir_dic: dictionary of names and sizes of files in the directory
        self.griddir: the type of grid directory that this directory is, l=lfc, s=surl
        self.last_file_name: name of last file in this directory

        """
        if CheckVomsProxy():
            raise self.Error('No valid proxy')
        SetGridEnv()

        self.dir=dir
        self.dir_dic={}
        self.griddir=''
        self.ND280Files=[]
        self.last_file_name=''

        ### Classify the directory type and check it's existance
        ## LFC Directories
        if 'lfn:' in self.dir:
            command = 'lfc-ls -l ' + self.dir.replace('lfn:','')
            lines,errors = runLCG(command, in_timeout=ls_timeout)
            if not errors:
                for line in lines:
                    ## very rarely get files without a name, skip directories in which the filename
                    ## field is blank
                    if len(line.split())<9:
                        print 'Skipping blank file!!!', line
                        
                    line_spl=line.split()
                    TotalFN=line_spl[len(line_spl)-1]
                    
                    ## Dictionary of file objects for quick useage/comparison
                    justFN=TotalFN.split('/')[len(TotalFN.split('/'))-1]
                    self.dir_dic[justFN] = line_spl[4]
                    ## List of ND280File objects
                    f=0
                    try:
                        f=ND280File(self.dir + '/' + justFN, check=False)
                    except:
                        message='Could not create ND280File with name ' + self.dir + '/' + justFN
                        if not skipFailures:
                            sys.exit(message)
                        else:
                            print message
                            print 'WARNING: '+justFN+' will be ignored!'
                    if f:
                        self.ND280Files.append(f)
                        
            else:
                raise self.Error('Could not list files in lfc directory' + self.dir)

            self.griddir='l'

        ### Local Directories
        else:
            if not os.path.isdir(self.dir):
                raise self.Error('This dir does not exist on the local system ' + self.dir)
            self.gridfile=''

            command = 'ls -l ' + self.dir
            lines,errors = runLCG(command,is_pexpect=False)
            if not errors:
                for line in lines:
                    
##                     ## First of all ignore local sub-directories
##                     if os.path.isdir(self.dir + '/' + file):
##                         continue

                    line_spl=line.split()
                    if len(line_spl) <5:
                        continue
                    TotalFN=line_spl[len(line_spl)-1]
                    justFN=TotalFN.split('/')[len(TotalFN.split('/'))-1]
                    self.dir_dic[justFN] = line_spl[4]
                    ## List of ND280File objects
                    f=0
                    try:
                        f=ND280File(self.dir + '/' + justFN, check=False)
                    except:
                        message='Could not create ND280File with name ' + self.dir + '/' + justFN
                        if not skipFailures:
                            sys.exit(message)
                        else:
                            print message
                    if f:
                        self.ND280Files.append(f)
            else:
                raise self.Error('Could not list files in local directory ' + self.dir)

        ### Last file name
        if len(self.ND280Files):
            self.last_file_name=self.ND280Files[len(self.ND280Files)-1].filename
            print 'Last file in '+self.dir+' is '+self.last_file_name

    ### Internal Error class for raising errors
    class Error(Exception):
        pass

    def Delete(self):
        """ Deletes all files in the ND280Dir """
        if self.griddir:
            for file,size in self.dir_dic.iteritems():
                command = 'lcg-del -a ' + self.dir + '/' + file
                lines,errors = runLCG(command)
                if errors:
                    raise self.Error('Could not remove file ', command, errors)
        return 0
    
    def HashDiff(self,other_dir):
        """ diff two differnet ND280 directories using file hashes        
        """

        ## compile lists of the self directory
        self.filehashes={}
        for f in self.ND280Files:
            self.filehashes[f.GetFileHash()]=(f)

        ## compile list of other directories
        other_dir.filehashes={}
        for f in other_dir.ND280Files:
            other_dir.filehashes[f.GetFileHash()]=(file)
            
        ## Do the comparisons
        diff_ls=[]
        
        for hash,file in self.filehashes.iteritems():
            if not hash in other_dir.filehashes:
                diff_ls.append(self.dir + file)
        for hash,file in other_dir.filehashes.iteritems():
            if not hash in self.filehashes:
                diff_ls.append(other_dir.dir + file)
        return diff_ls

    def RunDiff(self,other_dir):
        """ diff two different ND280 directories using run-subrun number
        """

        ## compile lists of the self directory
        self.runs={}
        for f in self.ND280Files:
            self.runs[f.GetRunNumber() + '-' + f.GetSubRunNumber()]=(f)

        ## compile list of other directory
        other_dir.runs={}
        for f in other_dir.ND280Files:
            other_dir.runs[f.GetRunNumber() + '-' + f.GetSubRunNumber()]=(f)
            
        ## Do the comparisons
        diff_ls=[]

        for run,f in self.runs.iteritems():
            if not run in other_dir.runs:
                diff_ls.append(f.path + f.filename)
        for run,f in other_dir.runs.iteritems():
            if not run in self.runs:
                diff_ls.append(f.path + f.filename)
        return diff_ls

    def SyncSRM(self,srm,use_fts=0,sync_pattern='',ftsInt=0):
        """ Synchronise this directory with a particular SRM """
        print 'SyncSRM()'
        failures  =0
        isLastFile=False
        good_files=[]

        # If sync_pattern==GOODFILES, only sync files in GoodFiles.list,
        # don't bother looking for files not in current directory!
        if sync_pattern == 'GOODFILES':
            good_list_name = os.getenv("ND280COMPUTINGROOT")+'/data_scripts/GoodRuns.list'
            #good_list_name = os.getenv("ND280COMPUTINGROOT")+'/data_scripts/GoodRuns.test'
            print 'Opening '+good_list_name
            good_list = open(good_list_name,'r')

            if good_list:
                print good_list_name+' open'
                
                # Read files
                good_files = good_list.readlines()

                # Get run range from first file in this directory
                run_range = self.ND280Files[0].GetRunRange()
                #run_range = 'File0'
                print 'RunRange:'+run_range
                good_files = [rmNL(file).replace('//','/') for file in good_files if file.__contains__(run_range)]

                print 'good_files:'
                for gf in good_files:
                    print gf
                
                good_list.close()
            else:
                raise self.Error('SyncSRM: Could not open '+good_list_name)
        
        for f in self.ND280Files:
            # Check whether this is the last file (important for FTS)
            if f.filename == self.last_file_name:
                if use_fts:
                    print f.filename+' is last file and using FTS'
                    isLastFile=True

            # Skip files not containing sync_pattern (unless last file)
            # if sync_pattern==GOODFILES, only sync files in GoodFiles.list
            if sync_pattern == 'GOODFILES' and good_files:
                if f.alias in good_files or isLastFile:
                    print 'Syncing GOODFILE: '+f.alias
                else:
                    print 'Skipping GOODFILE sync of '+f.alias
                    continue
            elif sync_pattern != 'GOODFILES' and not sync_pattern in f.filename and not isLastFile:
                continue

            # Try the copy
            try:
                print 'Try copying '+f.filename+' to '+srm
                # Always run FTS if on last file
                if (not f.OnSRM(srm)) or (isLastFile and use_fts):
                    f.CopySRM(srm,use_fts,isLastFile,ftsInt)
                else:
                    print 'Replica already exists!'
            except:
                failures+=1
                print 'SyncSRM Copy '+f.filename+' to srm: '+srm+'  failed'
                
        if failures:
            # Clean up FTS files
            if use_fts and TRANSFER_FILE_LIST:
                print 'Cleaning up FTS transfer files:'
                for channel in TRANSFER_FILE_LIST:
                    print 'Removing '+channel
                    if os.path.exists(channel):
                        os.remove(channel)
                    TRANSFER_FILE_LIST.remove(channel)
            raise self.Error('SyncSRM: Could not synchronise ' + str(failures) + ' files between ' + self.dir + ' and ' + str(srm))

    def SyncND280Dir(self,new_dir,srm='',sync_pattern=''):
        """ Method to synchronise two ND280Dirs """

        failures=0

        if self.griddir == new_dir.griddir:
            if self.griddir:
                raise self.Error('Trying to synchronise two lfc directories ' + self.dir + ' and ' + new_dir.dir)
            else:
                raise self.Error('Trying to synchronise two local directories ' + self.dir + ' and ' + new_dir.dir)
            
        if self.griddir:
            for f in self.ND280Files:
                # skip files not containing sync_pattern, '' always true
                if not sync_pattern in f.filename:
                    continue
                if not f.filename in new_dir.dir_dic:
                    try:
                        f.CopyLocal(new_dir.dir)
                    except:
                        failures+=1
                        print 'SyncND280Dir griddir Copy failed'
        else:
            for f in self.ND280Files:
                # skip files not containing sync_pattern, '' always true
                if not sync_pattern in f.filename:
                    continue
                if not f.filename in new_dir.dir_dic:
                    try:
                        f.Register(new_dir.dir + f.filename,srm)
                    except:
                        failures+=1
                        print 'SyncND280Dir ND280File Copy failed'
        if failures:
            raise self.Error('SyncND280Dir: Could not synchronise ' + str(failures) + ' files between ' + self.dir + ' and ' + str(srm))

    def NewSync(self,new_dir_name,fts_srm='',sync_pattern='',ftsInt=0):
        """ A generic sync
        new_dir_name=name of the directory to be copied to
        fts_srm= if new_dir_name is an srm then this option is a flag for fts use or not
                 if new_dir_name is for an LFC or local directory it is used to specify an srm to copy to.
        sync_pattern=only copy files matching <sync_pattern>
        ftsInt=optional integer to include in FTS transfer-file name
        """

        ##If we are trying to Synchronise with a surl over ride and use standard copying
        if 'srm://' in new_dir_name:
            srm=new_dir_name.split('/')[2]
            self.SyncSRM(srm,fts_srm,sync_pattern,ftsInt)
        else:
            new_dir=''
            try:
                new_dir=ND280Dir(new_dir_name)
            except:
                raise self.Error('Could not create ND280Dir ' + new_dir_name)

            self.SyncND280Dir(new_dir,fts_srm,sync_pattern)

#############################################################################################################
########### ND280JDL Class
#############################################################################################################
            
class ND280JDL:
    """ A class that defines a JDL file for a t2k.org job.
    Each of the following must be defined,

    jdlname       = The name of the jdl file which will be created
    nd280ver      = version of nd280 software which will be run
    input         = The name of the input file to process over: can be lfn, srm or local
    destination   = The destination for the output (currently redundant because of complicated directory structure of data)
    executable    = The executable to run
    arguments     = The arguments to pass to the executable
    inputsandbox  = A list of filname strings to include in the input sandbox of the Job
    outputsandbox = A list of filname strings to include in the output sandbox of the Job

    this can be done in a member function (as CreateRawJDLFile) or by hand in your code E.g.

    jdl = ND280JDL('v7r19p9','lfn:/grid/t2k.org/nd280....', 'lfn:/grid/t2k.org/nd280/new/...')
    jdl.jdlname = 'myjdlfile.jdl'
    jdl.inputsandbox = ['file1.sh', 'file2.txt', 'file3.py']
    ...
    ...

    """
    def __init__(self, nd280ver, input, jobtype, evtype='', options={}):
        """ Initialise the JDL object """
        self.nd280ver = nd280ver
        self.input = ND280File(input)
        self.jobtype = jobtype
        self.evtype = evtype
        self.options = options
        self.cfgfile = self.options['cfgfile']
        self.queuelim = '512'
        if self.options['regexp']:
            self.regexp = str(self.options['regexp'])
        if self.options['queuelim']:
            self.queuelim = str(self.options['queuelim'])
        if self.input.filetype=='r' or self.input.filetype=='p':
            if not self.options['trigger']:
                raise self.Error('The file ' + self.input.filename + ' is a raw data file, please specify the trigger type via the options[\'trigger\']')
            else:
                self.SetupProcessJDLFile()
        self.SetupProcessJDLFile()        

    ### Internal Error class for raising errors
    class Error(Exception):
        pass
    
    def CreateJDLFile(self,dir=''):
        """ Generic creation of a JDL file, all specifics are to be written in a setup function E.g. SetupProcessJDLFile """

        try:
            if not '.jdl' in self.jdlname:
                self.jdlname+='.jdl'
            if dir:
                self.jdlname=dir + '/' + self.jdlname
            jdlfile = open(self.jdlname,"w")

            jdlfile.write('Executable = \"' + self.executable + '\";\n')   # just a single string
            jdlfile.write('Arguments = \"' + self.arguments + '\";\n')

            comp_path=os.getenv('ND280COMPUTINGROOT')
            if not comp_path:
                raise self.Error('Could not get the ND280COMPUTINGROOT environment variable, have you executed the setup.sh?')

            input_SB_string='InputSandbox = {\"' + comp_path + '/tools/*.py\", \"' + self.executable + '\"'
            if self.cfgfile:
                input_SB_string += ', \"' + self.cfgfile + '\"'
            for j,i in enumerate(self.inputsandbox):
                input_SB_string+= ', \"' + i + '\"'
            input_SB_string+='};\n'
            jdlfile.write(input_SB_string)

            jdlfile.write('StdOutput = "' + self.stdoutput + '";\n')
            jdlfile.write('StdError = "'  + self.stderror + '";\n')

            output_SB_string='OutputSandbox = {"' + self.stdoutput + '", "'   + self.stderror + '"'
            for o in self.outputsandbox:
                output_SB_string+= ', "' + o + '"'
            output_SB_string+='};\n'
            jdlfile.write(output_SB_string)

            ## Data Requirements for LFC InputData
            jdlfile.write('DataRequirements = {\n[\nDataCatalogType = "DLI";\nDataCatalog = "'+os.getenv('LFC_HOST')+':8085/";\n')
            if self.input.alias and not 'cvmfs' in self.input.path:
                jdlfile.write('InputData = {"' + self.input.alias + '"};\n]\n};\n') ## Should use lcg-lr to determine where data is located.
            ## generic LFC Data Requirements
            else:
                jdlfile.write('InputData = {"lfn:/grid/t2k.org/nd280/cvmfsAccessList"};\n]\n};\n') ## The location of the replicas determine the resource matching
            jdlfile.write('DataAccessProtocol = {"gsiftp"};\n')



            ## VO requirements (ND280 software version etc)
            jdlfile.write('VirtualOrganisation = \"t2k.org\";\n')

            ## under CVMFS s/w tags no longer work
#            jdlfile.write('Requirements=Member(\"VO-t2k.org-ND280-' + self.nd280ver + '\",other.GlueHostApplicationSoftwareRunTimeEnvironment)')

            ## Resource requirements (CPU time, RAM etc)
#            jdlfile.write(' && other.GlueCEPolicyMaxCPUTime > 600')

            jdlfile.write('Requirements = other.GlueCEPolicyMaxCPUTime > 600')
            jdlfile.write(' && other.GlueHostMainMemoryRAMSize >= '+self.queuelim)
            #jdlfile.write('Requirements = other.GlueCEPolicyMaxCPUTime > 600 && other.GlueHostMainMemoryRAMSize >= '+self.queuelim)

            ## Add regexp to requirements? (to exclude sites etc)
            if self.options['regexp']:
                jdlfile.write(' && '+self.regexp)
            jdlfile.write(';\n')

            ## MyProxy server requirements
            if os.getenv('MYPROXY_SERVER'):
                jdlfile.write('MyProxyServer = \"'+os.getenv('MYPROXY_SERVER')+'\";\n')
            else:
                print 'Warning MyProxyServer attribute undefined!'

            ## Finished writing the JDL
            jdlfile.close()
            return self.jdlname
        except:
            print "Could not write create the " + self.jdlname + " jdl file"
        return ""

    ########################################################################################################################
    ##################### Setup functions for each job type ################################################################
    ########################################################################################################################
    
    def SetupProcessJDLFile(self):
        """ Create a Raw data or MC processing jdl file. The one and only argument is the event type to process: spill or cosmic trigger. """
  
        # Define the JDL file name... there are quite a few steps
        self.jdlname = 'ND280' + self.jobtype
        # Don't add trigger to JDL for non runND280 jobs
        if not self.jobtype in NONRUNND280JOBS:
            self.jdlname += '_' + str(self.options['trigger'])
        self.jdlname += '_' + self.nd280ver
        if 'fluka' in self.input.filename:
            self.jdlname += '_' + self.input.filename.rstrip('.root').replace('.','_')

            # parse custom options from options dict (repeat of what ND280Process does, needs a common method)
            if self.options['config']:
                config           = self.options['config'].replace("'","")
                custom_list_dict = {}
                for line in config.split(','):
                    if '=' in line:
                        key,value             = line.split('=')
                        custom_list_dict[key] = value
                
                if 'runCode' in custom_list_dict:
                    self.jdlname += '_' + custom_list_dict['runCode']

                # subrun = GetSubRunFromFlukaFileName(self.input.filename)
                subrun = 0

                if 'subrunOffset' in custom_list_dict:
                    subrun += int(custom_list_dict['subrunOffset'])
                self.jdlname += '_%04d' % (subrun)
                
        else:
            if self.input.GetRunNumber():
                self.jdlname += '_' + self.input.GetRunNumber() + '_' + self.input.GetSubRunNumber()
            else:
                self.jdlname += '_' + self.input.filename.rstrip('.root').replace('.','_')
            
        if self.input.filetype=='c':
            self.executable = 'ND280'+self.jobtype+'_testbeam.py'			
        elif self.input.filetype=='p':
            self.jdlname+='_' + self.input.GetFileHash() + '_' + self.input.GetStage()
            self.executable = 'ND280'+self.jobtype+'_process.py'
        else:
            self.executable = 'ND280'+self.jobtype+'_process.py'		
        self.jdlname+='.jdl'
        self.arguments = '-v ' + self.nd280ver

        if self.options['trigger'] and not self.jobtype in NONRUNND280JOBS:
            self.arguments += ' -e ' + str(self.options['trigger'])

        # Add optional arguments to line
        if self.options['prod']:
            self.arguments += ' -p ' + str(self.options['prod']) + ' -t ' + str(self.options['type'])
        if self.options['modules']:
            self.arguments += ' -m ' + str(self.options['modules'])
        if self.options['dirs']:
            self.arguments += ' -d ' + str(self.options['dirs'])
        if self.options['config']:
            self.arguments += " -c '" + str(self.options['config']) + "'"
        if self.options['dbtime']:
            self.arguments += ' -b ' + str(self.options['dbtime'])
        if self.options['generator']:
            self.arguments += ' -g ' + str(self.options['generator'])
        if self.options['geometry']:
            self.arguments += ' -a ' + str(self.options['geometry'])
        if self.options['vertex']:
            self.arguments += ' -y ' + str(self.options['vertex'])
        if self.options['beam']:
            self.arguments += ' -w ' + str(self.options['beam'])
        if 'neutVersion' in self.options:
            self.arguments += ' --neutVersion ' + self.options['neutVersion']
        if 'POT' in self.options:
            self.arguments += ' --POT ' + self.options['POT']
        if 'highlandVersion' in self.options:
            self.arguments += ' --highlandVersion ' + self.options['highlandVersion']
            
        ## Tools directory and the chosen executable are automatically included in InputSandbox
        self.inputsandbox = [] 

        ## If input is a local file, add it to InputSandbox and set the correct input path
        if not self.input.gridfile:
            localpath = self.input.path + self.input.filename
            if 'cvmfs' in self.input.path:
                self.input.alias = localpath
                self.arguments += ' -i ' + self.input.alias
            else:
                print 'Adding local input %s to InputSandbox' % (localpath)
                self.inputsandbox.append(localpath)
                self.arguments += ' -i ' + self.input.filename
        else:
            self.arguments += ' -i ' + self.input.alias
        
        # Define paths to stdout and stderr
        self.stdoutput = 'ND280'+self.jobtype+'.out'
        self.stderror  = 'ND280'+self.jobtype+'.err'
        cfgfn = GetConfigNameFromInput(self.input.filename)
        self.outputsandbox = [cfgfn]
        return 0

#############################################################################################################
########### ND280JID Class
#############################################################################################################
class ND280JID:
    """ A class that allows for a the checking and retriving of info from a JID file
    from previous script ~/GRIDTest/ND280Install/middle_processing/standard/CheckRunND280RunsStatus.py
    
    """
    def __init__(self, jidfile,jobno=''):
        """ Initialise the JDL object """
        self.jidfilename=jidfile
        self.jobno=jobno

        ## Variables which are to be modified
        self.status=''
        self.exitcode=''
        self.statusreason=''
        self.dest=''

        command = "glite-wms-job-status -i " + self.jidfilename
        child = pexpect.spawn(command)#,[], file)
        #### Get the min and max file number
        index = child.expect(['list - \[([0-9]+)\-?([0-9]+)\]?all:',pexpect.EOF,pexpect.TIMEOUT])
        if index==1: ## Just one file
            child = pexpect.spawn(command)
            self.jobno=1
        elif index==0:
            min,max = child.match.groups()
            ## If no job number specified then just go for the most recent
            if not self.jobno:
                self.jobno=max
            ## Check the requested jobno and if greater than max just choose the max
            if int(self.jobno)<=int(max):
                child.sendline(self.jobno)
            else:
                print "There are just ", max, " ids in this file so cannot choose ", self.jobno , " going with ", max
                child.sendline(max)
    
        #### Get the current status
        child.expect("Current Status: \s+([a-zA-Z0-9_]+)")
        self.status = child.match.groups()[0]

        if "Done" in self.status:
            ## print "Status: ", self.status
            child.expect("Exit code: \s+([0-9]+)")
            self.exitcode = child.match.groups()[0]
        
##        child.expect("Status Reason:  \s+(.+?)")
        child.expect("Status Reason:  \s+([a-zA-Z0-9_]+)")
        self.statusreason=child.match.groups()[0]

        if 'Done' in self.status or 'Running' in self.status or 'Scheduled' in self.status:
            child.expect("Destination:   \s+([a-zA-Z0-9_.]+)")
            self.dest=child.match.groups()[0]
            child.expect(pexpect.EOF)

    def GetStatus(self):
        return self.status

    def GetExitCode(self):
        return self.exitcode

    def GetStatusReason(self):
        return self.statusreason

    def GetDestination(self):
        return self.dest

    def GetRunNo(self):
        """ Get run number from standard format files """
        return self.jidfilename.split('_')[2]

    def GetSubRunNo(self):
        """ Get run number from standard format files """
        return self.jidfilename.split('_')[3].split('.')[0]

    def GetOutput(self):
        """ Get the output sandbox """
        outdir =self.jidfilename.replace('.jid','_'+self.jobno)
        command= 'glite-wms-job-output --dir ' + outdir + ' -i ' + self.jidfilename
        p      = Popen([command],shell=True,stdin=PIPE,stdout=PIPE,stderr=PIPE)
        lines  = p.stdout.readlines()
        errors = p.stderr.readlines()

        if errors:
            return ''
        return outdir
    
    ## A bunch of bool functions
    def IsDone(self):
        if 'Done' in self.status:
            return 1
        else:
            return 0
    def IsRunning(self):
        if 'Running' in self.status:
            return 1
        else:
            return 0
    def IsScheduled(self):
        if 'Scheduled' in self.status:
            return 1
        else:
            return 0

    def IsExitClean(self):
        if self.exitcode=='0':
            return 1
        else:
            return 0

########################################################################################################################

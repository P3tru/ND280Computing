#!/bin/bash

# Quick script to be run weekly by CRON to remove old data distribution logs

source ~/T2K/GRID/nd280Computing/data_scripts/cronGRID.sh

cd $ND280TRANSFERS

# Remove logs > 365 days old

let now=$(date +%s)
let limit=24*3600*365

for log in $(ls -1 | grep -E '.sync.|.reg.|cleanKEK.|production')
do 
  let old=$(stat -c %Z $log)
  let age=$(expr $now - $old)
  
  echo "Age of $log is $age"
  
  if(($age>$limit)); then
      echo "Removing $log"
      # rm -fv $log
  fi
done  

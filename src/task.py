#!/usr/bin/python

import reference_time
from time import sleep

import os, sys, re
import datetime
from copy import deepcopy
from time import strftime
import Pyro.core
import logging

global state_changed
#state_changed = False
state_changed = True

# NOTE ON TASK STATE INFORMATION---------------------------------------

# The only task attributes required for a CLEAN system start (i.e. from
# configured start time, rather than a previous dumped state) are:

#  (1) reference time
#  (2) state ('waiting', 'running', 'finished', or 'failed')

# The 'state' variable is initialised by the base class. The reference
# time is initialised by derived classes because it may be adjusted at
# start time according to the allowed values for each task type.  Both
# of these variables are written to the state dump file by the base
# class dump_state() method.

# For a restart from previous state, however, some tasks may require
# additional state information to be stored in the state dump file.
# Take, for instance, a task foo that runs hourly and depends on the
# most recent available 12-hourly task bar, but is allowed to run ahead
# of bar to some extent, and changes its behavior according whether or
# not it was triggered by a "old" bar (i.e. one already used by the
# previous foo instance) or a "new" one. In this case, currently, we
# use a class variable in task type foo to record the reference time of
# the most recent bar used by any foo instance. This is written to the
# the state dump file so that task foo does not have to automatically
# assume it was triggered by a "new" bar after a restart.

# To handle this difference in initial state information (between normal
# start and restart) task initialisation must use a default value of
# 'None' for the additional variables, and for a restart the task
# manager must instantiate each task with a flattened list of all the
# state values found in the state dump file.

# The abdication mechanism ASSUMES that the task manager creates the
# successor task as soon as the current task abdicates.

############ TASK BASE CLASS
class task_base( Pyro.core.ObjBase ):
    
    # Default task deletion: quick_death = True
    # This amounts to a statement that the task has only cotemporal
    # downstream dependents (i.e. the only other tasks that depend on it
    # to satisfy their prerequisites have the same reference time as it
    # does) and as such can be deleted at the earliest possible
    # opportunity - which is as soon as there are no non-finished
    # tasks with reference times the same or older than its reference
    # time (prior to that we can't be sure that an older non-finished 
    # task won't give rise (on abdicating) to a new task that does
    # depend on the task we're interested in). 

    # Tasks that are needed to satisfy the prerequisites of other tasks
    # in subsequent cycles, however, must set quick_death = False, in
    # which case they will be removed according to system cutoff time.
    quick_death = True

    @classmethod
    def describe( cls ):
        return cls.description 
        #for line in cls.description:
        #    print line


    def __init__( self, ref_time, abdicated, initial_state ):
        # Call this AFTER derived class initialisation
        # (which alters requisites based on initial state)

        # Derived classes MUST call nearest_ref_time() and define their 
        # prerequistes and outputs before calling this __init__.
        self.ref_time = ref_time

        # Has this object abdicated yet (used for recreating abdicated
        # tasks when loading tasks from the state dump file).
        self.abdicated = abdicated

        # count instances of each top level object derived from task
        # top level derived classes must define:
        #   <class>.instance_count = 0

        # task types that need to DUMP and LOAD MORE STATE INFORMATION
        # should override __init__() but make the new state variables
        # default to None so that they aren't required for normal
        # startup: __init__( self, initial_state, foo = None )
        # On reload from state dump the task manager will call the 
        # task __init__() with a flattened list of whatever state values 
        # it finds in the state dump file.

        self.__class__.instance_count += 1

        Pyro.core.ObjBase.__init__(self)

        # derived classes must define self.env_vars (environment
        # variables to export for use by my external task) AFTER
        # calling this base class init (or else the following default
        # setting will wipe them out).
        self.env_vars = []

        # set state_changed True if any task's state changes 
        # as a result of a remote method call
        global state_changed 
        state_changed = True

        # unique task identity
        self.identity = self.name + '%' + self.ref_time

        self.latest_message = ""

        if abdicated == 'True':
            # my successor has been created already
            self.abdicated = True
        else:
            # my successor has not been created yet
            self.abdicated = False 

        # initial states: 
        #  + waiting 
        #  + ready (prerequisites satisfied)
        #  + finished (outputs satisfied)
        if initial_state == "waiting": 
            self.state = "waiting"
        elif initial_state == "finished":  
            self.outputs.set_all_satisfied()
            self.prerequisites.set_all_satisfied()
            self.log( 'WARNING', " starting in FINISHED state" )
            #self.state = "finished"
            self.set_finished()
        elif initial_state == "ready":
            # waiting, but ready to go
            self.state = "waiting"
            self.log( 'WARNING', " starting in READY state" )
            self.prerequisites.set_all_satisfied()
        else:
            self.log( 'CRITICAL',  "unknown initial task state: " + initial_state )
            sys.exit(1)

        #self.log( 'DEBUG', "initial state: " + initial_state )


    def log( self, priority, message ):
        # task-specific log file

        # is it better to "get" this each time as here, or to get a
        # 'self.logger' once in __init__?
        logger = logging.getLogger( "main." + self.name ) 

        # task logs are already specific to type so we only need to
        # preface each entry with reference time, not whole task id.
        message = '[' + self.ref_time + '] ' + message

        if priority == "WARNING":
            logger.warning( message )
        elif priority == "NORMAL":
            logger.info( message )
        elif priority == "DEBUG":
            logger.debug( message )
        elif priority == "CRITICAL":
            logger.critical( message )
        else:
            logger.warning( 'UNKNOWN PRIORITY: ' + priority )
            logger.warning( '-> ' + message )


    def prepare_for_death( self ):
        # The task manager MUST call this immediately before deleting a
        # task object. It decrements the instance count of top level
        # objects derived from task_base. It would be nice to use Python's
        # __del__() function for this, but that is only called when a
        # deleted object is about to be garbage collected (which is not
        # guaranteed to be right away).

        # NOTE: this was once used for constraining the number of
        # instances of each task type. However, it has not been used
        # since converting to a global contraint on the maximum number
        # of hours that any task can get ahead of the slowest one.

        self.__class__.instance_count -= 1

    def nearest_ref_time( self, rt ):
        # return the next time >= rt for which this task is valid
        rh = int( rt[8:10])
        incr = None
        first_vh = self.valid_hours[ 0 ]
        extra_vh = 24 + first_vh 
        foo = deepcopy( self.valid_hours )
        foo.append( extra_vh )

        for vh in foo:
            if rh <= vh:
                incr = vh - rh
                break
    
        nearest_rt = reference_time.increment( rt, incr )
        return nearest_rt


    def next_ref_time( self, rt = None):
        # return the next reference time, or the next reference time
        # after rt, that is valid for this task.
        #--

        if not rt:
            # set proper default argument here (python does not allow
            # self.foo as a default argument)
            rt = self.ref_time

        n_times = len( self.valid_hours )
        if n_times == 1:
            increment = 24
        else:
            i_now = self.valid_hours.index( int( rt[8:10]) )
            # list indices start at zero
            if i_now < n_times - 1 :
                increment = self.valid_hours[ i_now + 1 ] - self.valid_hours[ i_now ]
            else:
                increment = self.valid_hours[ 0 ] + 24 - self.valid_hours[ i_now ]

        return reference_time.increment( rt, increment )


    def prev_ref_time( self ):
        # return the previous reference time valid for this task.
        #--

        rt = self.ref_time

        n_times = len( self.valid_hours )
        if n_times == 1:
            increment = 24
        else:
            i_now = self.valid_hours.index( int( rt[8:10]) )
            # list indices start at zero
            if i_now > 0 :
                decrement = self.valid_hours[ i_now ] - self.valid_hours[ i_now - 1 ] 
            else:
                decrement = self.valid_hours[ i_now ] - self.valid_hours[ n_times - 1 ] + 24

        return reference_time.decrement( rt, decrement )

    def run_if_ready( self, launcher, clock ):
        # run if I am 'waiting' AND my prequisites are satisfied
        if self.state == 'waiting' and self.prerequisites.all_satisfied(): 
            self.run_external_task( launcher )

    def run_external_task( self, launcher ):
        self.log( 'DEBUG',  'launching external task' )
        dummy_out = False
        launcher.run( self.owner, self.name, self.ref_time, self.external_task, dummy_out, self.env_vars )
        self.state = 'running'

    def get_state( self ):
        return self.name + ": " + self.state

    def display( self ):
        return self.name + "(" + self.ref_time + "): " + self.state

    def set_finished( self ):
        self.state = "finished"

    def is_complete( self ):  # not needed?
        if self.outputs.all_satisfied():
            return True
        else:
            return False

    def is_running( self ): 
        if self.state == "running":
            return True
        else:
            return False

    def is_finished( self ): 
        if self.state == "finished":
            return True
        else:
            return False

    def is_not_finished( self ):
        if self.state != "finished":
            return True
        else:
            return False

    def get_postrequisite_list( self ):
        return self.outputs.get_list()

    def get_timed_outputs( self ):
        return self.outputs.get_timed_requisites()

    def get_latest_message( self ):
        return self.latest_message

    def get_valid_hours( self ):
        return self.valid_hours

    def incoming( self, priority, message ):
        # receive all incoming pyro messages for this task 
        self.latest_message = message

        # set state_changed if this message satisfies any registered
        # output (indicates that the task manager needs to instigate a
        # new round of dependency renegotiations)
        global state_changed

        if self.state != "running":
            # my external task should not be running!
            self.log( 'WARNING', "UNEXPECTED MESSAGE (task should not be running)" )
            self.log( 'WARNING', '-> ' + message )

        # prefix task id to special messages.
        raw_message = message
        if message == 'started' or message == 'finished' or message == 'failed':
            message = self.identity + ' ' + message
 
        if self.outputs.exists( message ):
            # registered output messages

            if not self.outputs.is_satisfied( message ):
                # message indicates completion of a registered output.
                state_changed = True
                self.log( priority,  message )
                self.outputs.set_satisfied( message )

                if message == self.identity + ' finished':
                    # TASK HAS FINISHED
                    self.set_finished()
                    if not self.outputs.all_satisfied():
                        self.log( 'WARNING', 'finished before all outputs completed' )

            else:
                # this output has already been satisfied
                self.log( 'WARNING', "UNEXPECTED OUTPUT (already satisfied):" )
                self.log( 'WARNING', "-> " + message )

        elif raw_message == 'failed':
            # process task failure messages
            if priority != 'CRITICAL':
                self.log( 'WARNING', 'non-critical priority for task failure' )
            self.log( 'CRITICAL',  message )
            self.state = 'failed'

        else:
            # log other (non-failed) unregistered messages with a '*' prefix
            message = '*' + message
            self.log( priority, message )

    def update( self, reqs ):
        for req in reqs.get_list():
            if req in self.prerequisites.get_list():
                # req is one of my prerequisites
                if reqs.is_satisfied(req):
                    self.prerequisites.set_satisfied( req )

    def get_state_string( self ):
        # Derived classes should override this function if they require
        # non-standard state information to be written to the state dump
        # file.

        # Currently only single string values allowed, FORMAT: 
        #    state:foo:bar:baz (etc.)

        return self.state


    def get_real_time_delay( self ):
        # Return hours after reference to start running.
        # Used by dummy contact tasks in dummy mode.
        # Default, here, is to return None, which implies not a contact task
        # returning 0 => contact task starts running at reference time
        return None

    def dump_state( self, FILE ):
        # Write state information to the state dump file, reference time
        # first to allow users to sort the file easily in case they need
        # to edit it:
        #   reftime name abdicated state

        # Derived classes can override get_state_string() to add
        # information to the state dump file.
        
        # This must be compatible with __init__() on reload

        FILE.write( self.ref_time           + ' ' + 
                    self.name               + ' ' + 
                    str(self.abdicated)     + ' ' + 
                    self.get_state_string() + '\n' )


    def abdicate( self ):
        # the task manager should instantiate a new task when this one
        # abdicates (which only happens once per task). 
        if self.has_abdicated():
            return False

        if self.ready_to_abdicate():
            self.abdicated = True
            return True
        else:
            return False


    def set_abdicated( self ):
        self.abdicated = True


    def has_abdicated( self ):
        return self.abdicated

    def has_failed( self ):
        if self.state == 'failed':
            return True
        else:
            return False
            
    def ready_to_abdicate( self ):
        # DERIVED CLASSES MUST OVERRIDE THIS METHOD
        print 'ERROR, illegal task base method called!'
        self.log( 'CRITICAL', 'illegal task base method called!' )
        sys.exit(1)

    def done( self ):
        # return True if task has finished and abdicated
        if self.state == "finished" and self.has_abdicated():
            return True
        else:
            return False

    def get_state_summary( self ):
        # derived classes can call this method and then 
        # add more information to the summary if necessary.

        n_total = self.outputs.count()
        n_satisfied = self.outputs.count_satisfied()

        summary = {}
        summary[ 'name' ] = self.name
        summary[ 'short_name' ] = self.short_name
        summary[ 'state' ] = self.state
        summary[ 'reference_time' ] = self.ref_time
        summary[ 'n_total_outputs' ] = n_total
        summary[ 'n_completed_outputs' ] = n_satisfied
        summary[ 'abdicated' ] = self.has_abdicated()
        summary[ 'latest_message' ] = self.latest_message
 
        return summary

############ MAIN TASK CLASS FOR NON FORECAST MODELS
class general_purpose( task_base ):

    # Tasks with no previous instance dependence can in principle
    # abdicate immediately, but this creates waiting tasks out to the
    # max runahead, which clutters up monitor views and carries some
    # task processing overhead.
            
    # Waiting until they are running prevents excess waiting tasks
    # without preventing instances from running in parallel if the
    # opportunity arises.
            
    # BUT this does mean that a failed or lame task's successor won't
    # exist until the system operator abdicates and kills the offender.

    # Note that tasks with no previous instance dependence and  NO
    # PREREQUISITES will all "go off at once" out to the runahead 
    # limit (unless they are contact tasks whose time isn't up yet). 
    # These can be constrained with the sequential attribute if
    # that is preferred. 
 
    def ready_to_abdicate( self ):

        if self.has_abdicated():
            # already abdicated
            return False

        if self.state == 'finished':
            # always abdicate a finished task
            return True

        if self.state == 'running':
            # see documentation above
            return True

############ MAIN TASK CLASS FOR FORECAST MODELS
class forecast_model( task_base ):

    # Forecast models have previous instance dependence via their
    # restart files. Never abdicate a waiting task of this type because
    # the successor's restart prerequisites could get satisfied by the
    # later restart outputs of an earlier previous instance, and thereby
    # start too soon (we want this to happen ONLY if the previous task
    # fails and is subsequently abdicated-and-killed by the system operator).

    def register_restarts( self, output_times ):
        # call after parent init, so that self.ref_time is defined!

        msg = self.name + ' restart files ready for '
        self.prerequisites.add(  msg + self.ref_time )

        rt = self.ref_time
        for t in output_times:
            next_rt = self.next_ref_time( rt )
            self.outputs.add( t, msg + next_rt )
            rt = next_rt

    def ready_to_abdicate( self ):

        if self.has_abdicated():
            # already abdicated
            return False

        if self.state == 'finished':
            # always abdicate a finished task
            return True

        ready = False

        if self.state == 'running' or self.state == 'failed': 
            # failed tasks are running before they fail, so will already
            # have abdicated, or not, according to whether they fail
            # before or after completing their restart outputs.

            # ready only if all restart outputs are completed
            # as explained above

            ready = True
            for message in self.outputs.satisfied.keys():
                if re.search( 'restart files ready', message ) and not self.outputs.satisfied[ message ]:
                    ready = False
                    break

        return ready


############ TASK CLASS ATTRIBUTES FOLLOW

# USE MULTIPLE INHERITANCE TO DERIVE FINAL TASK CLASSES WITH ATTRIBUTES
# Precedence is left first, e.g.:
#     class foo( oneoff, contact, general_purpose ):
#           pass

class contact:
    # A task that waits on external events such as incoming external
    # data. These are the only tasks that can know if they are are
    # "caught up" or not, according to how their reference time relates
    # to current clock time.

    # The real contact task, once running (which occurs when all of its
    # prerequistes are satisfied), returns only when the external event
    # has occurred. This will be approximately after some known delay
    # relative to the task's reference time (e.g. data arrives 15 min
    # past the hour).  This delay interval needs to be defined for
    # accurate dummy mode simulation.  In catch up operation the
    # external task returns immediately because the external event has
    # already happened (i.e. the required data already exists).

    def __init__( self, relative_state ):

        # catch up status is held as a class variable
        # (i.e. one for each *type* of task proxy object) 
        if relative_state == 'catching_up':
            self.__class__.catchup_mode = True
        else:
            # 'caught_up'
            self.__class__.catchup_mode = False

        # Catchup status needs to be written to the state dump file so
        # that we don't need to assume catching up at restart. 
        # Topnet, via its fuzzy prerequisites, can run out to
        # 48 hours ahead of nzlam when caught up, and only 12 hours
        # ahead when catching up.  Therefore if topnet is 18 hours, say,
        # ahead of nzlam when we stop the system, on restart the first
        # topnet to be created will have only a 12 hour fuzzy window,
        # which will cause it to wait for the next nzlam instead of
        # running immediately.

        # CHILD CLASS MUST DEFINE:
        #   self.real_time_delay
 

    def get_real_time_delay( self ):
        return self.real_time_delay


    def get_state_string( self ):
        # for state dump file
        # see comment above on catchup_mode and restarts

        if self.__class__.catchup_mode:
            relative_state = 'catching_up'
        else:
            relative_state = 'caught_up'

        return self.state + ':' + relative_state


    def get_state_summary( self ):
        summary = task_base.get_state_summary( self )
        summary[ 'catching_up' ] = self.__class__.catchup_mode
        return summary


    def run_if_ready( self, launcher, clock ):
        # run if ready *and* the contact delay time is up (there's no
        # point in running earlier as the task will just sit in the
        # queue waiting on the external event).

        if self.state == 'waiting' and self.prerequisites.all_satisfied():

            # check current time against expected start time
            rt = reference_time._rt_to_dt( self.ref_time )
            delayed_start = rt + datetime.timedelta( 0,0,0,0,0,self.real_time_delay,0 ) 
            current_time = clock.get_datetime()

            if current_time >= delayed_start:
                # time to run the task

                self.log( 'DEBUG', 'delayed start time has already passed' )
                if self.__class__.catchup_mode:
                    # already catching up
                    pass
                else:
                    # don't reset catchup_mode once catchup has occurred.
                    self.log( 'DEBUG',  'falling behind' )

                # run the external task
                self.run_external_task( launcher )

            else:
                # not yet time to run the task
                
                if self.__class__.catchup_mode:
                    self.log( 'DEBUG',  'just caught up' )
                    self.__class__.catchup_mode = False
                else:
                    # keep waiting 
                    pass

class oneoff:
    # instances of this class always claim they have abdicated already
    def has_abdicated( self ):
        return True

class sequential:
    # instances of this class are not "ready to abdicate" unless they
    # have achieved the 'finished' state.
    def ready_to_abdicate( self ):
        if self.has_abdicated():
            return False
        if self.state == 'finished':
            # only abdicate if finished
            return True
        else:
            return False

class dummy:
    # instances of this class always launch a dummy task, even in real mode

    def __init__( self ):
        self.external_task = 'NO_EXTERNAL_TASK'

    def run_external_task( self, launcher ):
        self.log( 'DEBUG',  'launching external dummy task' )
        dummy_out = True
        launcher.run( self.owner, self.name, self.ref_time, self.external_task, dummy_out, self.env_vars )
        self.state = 'running'



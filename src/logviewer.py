#!/usr/bin/env python

import gtk
import pygtk
####pygtk.require('2.0')
import time, os, re, sys
from warning_dialog import warning_dialog

from logview import tailer

class logviewer:
    def __init__( self, name, dir, file ):
        self.name = name
        self.dir = dir
        self.file = file
        
        self.find_current = None
        self.find_current_iter = None
        self.search_warning_done = False

        self.create_gui_panel()

        self.t = tailer( self.logview, self.path() )
        print "Starting log viewer thread for " + self.name
        self.t.start()
    
    def path( self ):
        if self.dir:
            return self.dir + '/' + self.file
        else:
            return self.file

    def quit_w_e( self, w, e ):
        self.t.quit = True

    def quit( self ):
        self.t.quit = True

    def get_widget( self ):
        return self.vbox

    def reset_logbuffer( self ):
        # clear log buffer iters and tags
        logbuffer = self.logview.get_buffer()
        s,e = logbuffer.get_bounds()
        logbuffer.remove_all_tags( s,e )
        self.find_current_iter = None
        self.find_current = None

    def enter_clicked( self, e, tv ):
        self.on_find_clicked( tv, e )

    def on_find_clicked( self, tv, e ):
        needle = e.get_text ()
        if not needle:
            return

        self.t.freeze = True
        self.freeze_button.set_active(True)
        self.freeze_button.set_label('UnFreeze')
        if not self.search_warning_done:
            warning_dialog( "Find Next detaches the live log feed; click UnFreeze when you're done" ).warn()
            self.search_warning_done = True

        tb = tv.get_buffer ()

        if needle == self.find_current:
            s = self.find_current_iter
        else:
            s,e = tb.get_bounds()
            tb.remove_all_tags( s,e )
            s = tb.get_end_iter()
            tv.scroll_to_iter( s, 0 )
        try:
            f, l = s.backward_search (needle, gtk.TEXT_SEARCH_TEXT_ONLY) 
        except:
            warning_dialog( '"' + needle + '"' + " not found" ).warn()
        else:
            tag = tb.create_tag( None, background="#70FFA9" )
            tb.apply_tag( tag, f, l )
            self.find_current_iter = f
            self.find_current = needle
            tv.scroll_to_iter( f, 0 )

    def freeze_log( self, b ):
        # TO DO: HANDLE MORE STUFF IN THREADS LIKE THIS, RATHER THAN
        # PASSING IN ARGUMENTS?
        if b.get_active():
            self.t.freeze = True
            b.set_label( 'UNFREEZE' )
            self.reset_logbuffer()
        else:
            self.t.freeze = False
            b.set_label( 'Freeze' )

        return False


    def create_gui_panel( self ):
        self.logview = gtk.TextView()
        self.logview.set_editable( False )

        searchbox = gtk.HBox()
        entry = gtk.Entry ()
        entry.connect( "activate", self.enter_clicked, self.logview )
        searchbox.pack_start (entry, True)
        b = gtk.Button ("Find Next")
        b.connect_object ('clicked', self.on_find_clicked, self.logview, entry)
        searchbox.pack_start (b, False)

        self.hbox = gtk.HBox()
        self.log_label = gtk.Label( self.name )
        #self.log_label.modify_fg( gtk.STATE_NORMAL, gtk.gdk.color_parse( "#f00" ))
        self.hbox.pack_start( self.log_label, True )

        self.freeze_button = gtk.ToggleButton( "Freeze" )
        self.freeze_button.set_active(False)
        self.freeze_button.connect("toggled", self.freeze_log )
        self.hbox.pack_end( self.freeze_button, False )

        sw = gtk.ScrolledWindow()
        sw.set_policy( gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC )
        sw.add( self.logview )

        self.vbox = gtk.VBox()
        self.vbox.pack_start( sw, True )
        self.vbox.pack_start( searchbox, False )
        self.vbox.pack_start( self.hbox, False )

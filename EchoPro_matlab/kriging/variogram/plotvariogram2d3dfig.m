function 	plotvariogram2d3dfig(opt)
%% function plotvariogram2d3dfig(opt) establishes a GUI configuration for
%% displaying 2D/3D semi-variogram/correlogram.
% opt = 1	:   initial or re-plot with a new set of variogram/correlogram
%     = 2   :   replot selected 
%%
%%  Kriging Software Package  version 3.0,   May 1, 2004
%%  Copyright (c) 1999, 2001, 2004, property of Dezhang Chu and Woods Hole Oceanographic
%%  Institution.  All Rights Reserved.

global para hdl data color

grey=color.grey;
dark_grey=color.dark_grey;
blue=color.blue;

if ~isempty(findobj('type','figure','Tag','DisplayVario2D3D'))
    figure(hdl.dispvario2d3d.h0);
else
    %% create 2-D semi-variogram/correlogram window
    hdl.dispvario2d3d.h0 = figure('Units','normalized', ...
        'Color',[0.8 0.8 0.8], ...
        'Name','Display 2D/3D Variogram/Correlogram', ...
        'Position',hdl.window_position, ...
        'Tag','DisplayVario2D3D');
    if 0
        set(0, 'showhidden', 'on');
        ch=get(gcf, 'children');
        get(ch(2:length(ch)), 'label');
        delete(ch(2));
        %	delete(ch(4));
        %	delete(ch(5));
        %	delete(ch(6));
    end
    if 1
        set(0, 'showhidden', 'on')
        ch=get(gcf, 'children');
        %	delete(ch(3))								%Tools
        wmhdl=findobj(ch,'Label','&Tools');
        delete(wmhdl);
        ch(find(ch == wmhdl))=[];
        %     new feature in V6.x delete(ch(6))			%Edit
        wmhdl=findobj(ch,'Label','&Edit');
        delete(wmhdl);
        ch(find(ch == wmhdl))=[];
        %      new feature in V6.x                      %insert
        wmhdl=findobj(ch,'Label','&Insert');
        delete(wmhdl);
        ch(find(ch == wmhdl))=[];
        %      new feature in V6.x                      %View
        wmhdl=findobj(ch,'Label','&View');
        delete(wmhdl);
        ch(find(ch == wmhdl))=[];
        %      new feature of V7.0
        wmhdl=findobj(ch,'Label','&Desktop');	    %Desktop
        if ~isempty(wmhdl)
            delete(wmhdl);
            ch(find(ch == wmhdl))=[];
        end
    end
    Filehdl=findobj(ch,'Label','&File');
    ch_file=get(Filehdl,'children');
    %% ch_file   1  '&Print...'
    %            2  'Print Pre&view...'
    %            3  'Print Set&up...'
    %            4  'Pa&ge Setup...'
    %            5  'Pre&ferences...'
    %            6  '&Export...'
    %            7  'Save &As...'
    %            8  '&Save'
    %            9  '&Close'
    %           10  '&Open...'
    %           11  '&New Figure'
    set(findobj(ch_file(1:end),'Label','&Open...'),'Label','&Load','callback','file_browser3d(2,2);')
    %delete(ch_file([11 8 7 6 5]));
    
    hdl_quit=uimenu(hdl.dispvario2d3d.h0,'label','Quit','Callback','close_window(5)','separator','on');
    
    hdl.dispvario2d3d.axes1 = axes('Parent',hdl.dispvario2d3d.h0, ...
        'Color',[1 1 1], ...
        'Position',[0.15 0.4 0.6 0.5], ...
        'Tag','variogramAxes2');
    
    %%% zdir
    x0z=0.65;y0z=0.7;Lslider=0.15;
    dx=0.06;
    Ltext=0.1;
    Ly=0.04;Lx=0.1;
    Lradio=0.08;
    EPS=0.001;
    
    if para.status.variogramfig  == 1
        xstep=1/para.vario.nazm;
        zstep=1/para.vario.ndip;
    else
        xstep=0.05;
        zstep=0.05;
    end
    
    
    %%% slice variation
    x0x=0.3;y0x=0.25;Lslider=0.12;
    dy=0.06;
    Lradio=0.13;
    Lx=0.08;Ly=0.05;
    Ltext=Lx+Lslider;
    
    if para.vario.dim == 3 & para.vario.nazm > 1
        %%% azimuth
        hdl.dispvario2d3d.azm_radio = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',dark_grey, ...
            'Callback','radio_action_vario2d3d(1)', ...
            'HorizontalAlignment','center', ...
            'FontWeight','bold', ...
            'Position',[x0x y0x+0.003 Ltext Ly-0.01], ...
            'String','Azimuth Angle', ...
            'value',0, ...
            'Style','radio');
        hdl.dispvario2d3d.azm_val = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',[1 1 1], ...
            'FontWeight','bold', ...
            'Position',[x0x y0x-dy Lx Ly ], ...
            'Style','edit');
        hdl.dispvario2d3d.azm_slider = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',dark_grey, ...
            'Callback','plotvariogram2d3d(2)', ...
            'SliderStep',[xstep-EPS xstep+EPS], ...
            'Position',[x0x+Lx y0x-dy Lslider Ly ], ...
            'Style','slider');
    end
    
    if para.vario.dim == 3 & para.vario.ndip > 1
        
        %% dip
        hdl.dispvario2d3d.dip_radio = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',dark_grey, ...
            'Callback','radio_action_vario2d3d(2)', ...
            'HorizontalAlignment','center', ...
            'FontWeight','bold', ...
            'Position',[x0z y0z+Ly Lx+Ly Ly-0.01], ...
            'String','Dip Angle', ...
            'value',1, ...
            'Style','radio');
        hdl.dispvario2d3d.dip_val = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',[1 1 1], ...
            'FontWeight','bold', ...
            'Position',[x0z y0z Lx+0.015 Ly ], ...
            'Style','edit');
        hdl.dispvario2d3d.dip_slider = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
            'Units','normalized', ...
            'BackgroundColor',dark_grey, ...
            'Callback','plotvariogram2d3d(3)', ...
            'SliderStep',[zstep-EPS zstep+EPS], ...
            'Position',[x0z+Lx+0.015 y0z-Ly-0.02 Ly-0.015 Lslider], ...
            'Style','slider');
    end
    
    %% color scale adjustment
    x0cs=0.82;
    y0cs1=0.75;
    y0cs2=0.40;
    Lycs=0.025;
    hdl.dispvario2d3d.cbar_slider_top = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'BackgroundColor',dark_grey, ...
        'Callback','plotvariogram2d3d(4)', ...
        'SliderStep',[0.01-EPS 0.01+EPS], ...
        'Position',[x0cs y0cs1 Lycs Lslider], ...
        'Style','slider','value',1.0);
    hdl.dispvario2d3d.cbar_slider_bot = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'BackgroundColor',dark_grey, ...
        'Callback','plotvariogram2d3d(4)', ...
        'SliderStep',[0.01-EPS 0.01+EPS], ...
        'Position',[x0cs y0cs2 Lycs Lslider], ...
        'Style','slider','value',0);
    
    
    %%	shading
    hdl.dispvario2d3d.shading_index=1;
    Lradio=0.12;
    Ly=0.04;
    x0=0.63;
    y0=0.3;
    dy=0.05;
    h1 = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'BackgroundColor',dark_grey, ...
        'HorizontalAlignment','center', ...
        'FontWeight','bold', ...
        'Position',[x0 y0 Lradio Ly], ...
        'String','Shading', ...
        'Style','text');
    hdl.dispvario2d3d.shading_radio1 = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'Callback','radio_action_vario2d3d(3)', ...
        'String','Faceted', ...
        'Position',[x0 y0-dy Lradio Ly], ...
        'value',0, ...
        'Style','radio');
    hdl.dispvario2d3d.shading_radio2 = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'Callback','radio_action_vario2d3d(4)', ...
        'String','Flat', ...
        'Position',[x0 y0-2*dy Lradio Ly], ...
        'Style','radio');
    hdl.dispvario2d3d.shading_radio3 = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'Callback','radio_action_vario2d3d(5)', ...
        'String','Interp', ...
        'value',1, ...
        'Position',[x0 y0-3*dy Lradio Ly], ...
        'Style','radio');
    
    %% Push button
    h1 = uicontrol('Parent',hdl.dispvario2d3d.h0, ...
        'Units','normalized', ...
        'Callback','close_window(5)', ...
        'FontSize',10, ...
        'FontWeight','bold', ...
        'Position',[0.82 0.08 0.10 0.05], ...
        'String','Quit');
    
    axis square
    hdl.dispvario2d3d.colorbar2=colorbar;
    set(hdl.dispvario2d3d.colorbar2,'Position',[0.85 0.4 0.045 0.5]);
    %set(hdl.dispvario2d3d.colorbar2,'visible','off');
    %set(get(hdl.dispvario2d3d.colorbar2,'children'),'visible','off');
    hdl.status.dispvario2d3d=1;
end



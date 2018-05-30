/*
 * Copyright (C) 2015-2018 EDF SA
 *
 * This file is part of jobmetrics.
 *
 * jobmetrics is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * jobmetrics is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with jobmetrics.  If not, see <http://www.gnu.org/licenses/>.
 */

var cluster = null;
var job = null;
var period = '1h'; // default period
var plot = null;
var debug = false;
var updateInterval = 10 * 1000; // 10 seconds
var update_timeout = null;

function getUrlParameter(sParam) {
    var sPageURL = decodeURIComponent(window.location.search.substring(1)),
        sURLVariables = sPageURL.split('&'),
        sParameterName,
        i;

    for (i = 0; i < sURLVariables.length; i++) {
        sParameterName = sURLVariables[i].split('=');

        if (sParameterName[0] === sParam) {
            return sParameterName[1] === undefined ? true : sParameterName[1];
        }
    }
};

function process_metrics_result(result) {

    var cpu_user = new Array;
    var cpu_system = new Array;
    var cpu_idle = new Array;
    var cpu_iowait = new Array;
    var cpu_softirq = new Array;
    var gpu_scale_max = 0;
    var cpu_scale_max = 0;
    var memory_pss = new Array;
    var memory_rss = new Array;
    var utilization_gpu = new Array;
    var utilization_memory = new Array;
    var plots = new Array();
    var utc_offset_msec = new Date().getTimezoneOffset() * 60 * 1000;

    $.each(result, function( timestamp_utc, values ) {
	if (values[7] > gpu_scale_max)
		gpu_scale_max=values[7];
	if (values[9] > cpu_scale_max)
		cpu_scale_max=values[9];
    });   

    $.each(result, function( timestamp_utc, values ) {
        var timestamp = parseInt(timestamp_utc) - utc_offset_msec;
        cpu_system.push([timestamp, values[0]/cpu_scale_max]);
        cpu_iowait.push([timestamp, values[1]/cpu_scale_max]);
        cpu_user.push([timestamp, values[2]/cpu_scale_max]);
        cpu_softirq.push([timestamp, values[3]/cpu_scale_max]);
        cpu_idle.push([timestamp, values[4]/cpu_scale_max]);
        memory_pss.push([timestamp, values[5]/(1024*1024*1024)]);
        memory_rss.push([timestamp, values[6]/(1024*1024*1024)]);
	utilization_gpu.push([timestamp, values[7]*100/gpu_scale_max]);
        utilization_memory.push([timestamp, values[8]]);
    });
    
    plots = [
        { data: cpu_system,
          color: "rgba(204,0,0,1)",
          label: "CPU system %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
        { data: cpu_iowait,
          color: "rgba(255,204,0,1)",
          label: "CPU I/O wait %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
        { data: cpu_user,
          color: "rgba(204,153,255,1)",
          label: "CPU user %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
        { data: cpu_softirq,
          color: "rgba(104,153,255,1)",
          label: "CPU softirq %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
        { data: cpu_idle,
          color: "rgba(115,210,22,1)",
          label: "CPU idle %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
    ];
    if (!hide_pss) {
	plots.push(
            { data: memory_pss,
              color: "rgba(52,101,164,1)",
              label: "GiB memory (PSS)",
              yaxis: 2
            }
        );
    }
    if (!hide_rss) {
	plots.push(
            { data: memory_rss,
              color: "rgba(26,198,224,1)",
              label: "GiB memory (RSS)",
              yaxis: 2
            }
	);
    }
    plots.push(
	    { data: utilization_gpu,
	      color: "rgba(52,1,164,1)",
              label: "GPU %",
            },
            { data: utilization_memory,
              color: "rgba(152,1,64,1)",
              label: "GPU Memory %",
            }
    );
    return plots;

}


function set_period(new_period) {
    console.log("period is: " + new_period);
    period = new_period;
    update();
}

function init_period_links() {
    $('#period-1h').click(function(){ set_period('1h'); return false; });
    $('#period-6h').click(function(){ set_period('6h'); return false; });
    $('#period-24h').click(function(){ set_period('24h'); return false; });
}

function init_debug_zone() {

    if (debug === true) {
        $('#debug-button').empty();
        $('#debug-button').append('<img src="static/debug.png"/>');
        $('#debug-button').click(function() {
            $('#debug-modal').modal('toggle')
        });
    }
}

function update_debug_modal(debug_info) {

    $('#debug-modal-content').empty();
    content = "<h5>metadata</h5>" +
              "<ul>";

    Object.keys(debug_info['metadata']).forEach(function (key) {
        content += "<li><span class='debug-key'>" + key + ":</span> "
                 + debug_info['metadata'][key] + "</li>";
    });

    content += "</ul>" +
               "<h5>timers</h5>" +
               "<ul>";

    Object.keys(debug_info['timers']).forEach(function (key) {
        content += "<li><span class='debug-key'>"+ key + ":</span> "
                 + (debug_info['timers'][key]).toFixed(3) + " s</li>";
    });

    $('#debug-modal-content').append(content);
}

function show_error(status, error) {
    var $box = $('#error');
    $box.append("<strong>error " + status + ":</strong> " + error.error);
    $box.show();
}

function update(options) {

    if (update_timeout != null)
        clearTimeout(update_timeout);
    base_api = "/jobmetrics-restapi"
    api = base_api + "/metrics/" + cluster + "/" + job + "/" + period;
    $.ajax({
        url: api,
        dataType: "json" })
      .done( function(result){
        if (plot === null) {
            // initialize on first call if null
            plot = $.plot("#placeholder", process_metrics_result(result), options);

            // Add labels to both Y-axis. Their absolute positions are
            // calculated based on their width with combination of
            // top/margin-top to set their height. They are also 'transformed'
            // in the CSS to rotate them by 90 or -90°.
            var yaxis_cpu_label = $("<div class='axisLabel yaxisLabel yaxis1Label'></div>")
                                  .text("CPU/GPU usage & GPU Memory (%)")
                                  .appendTo("#placeholder");

            yaxis_cpu_label.css("margin-top", yaxis_cpu_label.width() / 2);
            yaxis_cpu_label.css("left", "-8px");

            var yaxis_mem_label = $("<div class='axisLabel yaxisLabel yaxis2Label'></div>")
                                  .text("Memory consumption (GiB)")
                                  .appendTo("#placeholder");

            yaxis_mem_label.css("margin-top", -yaxis_mem_label.width() / 2);
            yaxis_mem_label.css("right", -yaxis_mem_label.width());
        }
        plot.setData(process_metrics_result(result['data']));
        // Since the axes don't change, we don't need to call plot.setupGrid()
        plot.setupGrid();
        plot.draw();
        update_timeout = setTimeout(function() {
            update(options);
          }, updateInterval);
        update_debug_modal(result['debug']);
      })
      .fail( function(jqXHR, textStatus, errorThrown) {
        show_error(jqXHR.status, $.parseJSON(jqXHR.responseText));
      });

}

function set_title() {

    $('#header').empty();
    $('#header').append("<h2>HPC metrics:&nbsp;</h2>");
    $('h2').append("cluster " + cluster +" job " + job);
    $('title').empty();
    $('title').append("HPC metrics: job " + job);

}

function draw_diagram() {

    job = getUrlParameter('job');
    cluster = getUrlParameter('cluster');
    debug = ( getUrlParameter('debug') === 'true' );
    hide_pss = ( getUrlParameter('hide_pss') === 'true' );
    hide_rss = ( getUrlParameter('hide_rss') === 'true' );

    init_period_links();
    init_debug_zone();
    set_title(cluster, job);

    var options = {
        grid: {
          labelMargin: 10,
          margin: {
            left: 20,
            right: 20
          },
        },
        lines: {
            lineWidth: 1
        },
        xaxes: [ {
            mode: "time",
            tickLength: 5,
            position: 'bottom'
        } ],
        yaxes: [
          { min: 0 },
          {
            min: 0,
            // align if we are to the right
            alignTicksWithAxis: 1,
            position: "right"
          }
        ],
        legend: {
            position: "sw"
        },
        selection: {
            mode: "x"
        }
    };

    update(options);

}

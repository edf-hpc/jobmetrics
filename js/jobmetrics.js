// helper for returning the weekends in a period

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

function weekendAreas(axes) {

    var markings = [],
        d = new Date(axes.xaxis.min);

    // go to the first Saturday

    d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 1) % 7))
    d.setUTCSeconds(0);
    d.setUTCMinutes(0);
    d.setUTCHours(0);

    var i = d.getTime();

    // when we don't set yaxis, the rectangle automatically
    // extends to infinity upwards and downwards

    do {
        markings.push({ xaxis: { from: i, to: i + 2 * 24 * 60 * 60 * 1000 } });
        i += 7 * 24 * 60 * 60 * 1000;
    } while (i < axes.xaxis.max);

    return markings;
}

function process_metrics_result(result) {

    var cpu_user = new Array;
    var cpu_system = new Array;
    var cpu_idle = new Array;
    var memory_pss = new Array;

    $.each(result, function( timestamp, values ) {
        cpu_user.push([timestamp, values[1]]);
        cpu_system.push([timestamp, values[2]]);
        cpu_idle.push([timestamp, values[3]]);
        memory_pss.push([timestamp, values[4]/(1024*1024)]);
    });

    return [
        { data: cpu_system,
          color: "rgba(204,0,0,1)",
          label: "CPU system %",
          stack: true,
          lines: {
            show: true,
            fill: true,
          }
        },
        { data: cpu_user,
          color: "rgba(245,121,0,1)",
          label: "CPU user %",
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
        { data: memory_pss,
          color: "rgba(52,101,164,1)",
          label: "MB memory",
          yaxis: 2
        }
    ];

}

function show_job_diagram() {
    draw_diagram();
}

function draw_diagram() {

    var job = getUrlParameter('job');
    var cluster = getUrlParameter('cluster');

    $('#header').empty()
    $('#header').append("<h2>Cluster " + cluster + " job " + job + "</h2>")

    var options = {
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
        },
        grid: {
            markings: weekendAreas
        }
    };


    var updateInterval = 10 * 1000; // 10 seconds

    var api = "/jobmetrics-restapi/metrics/" + cluster + "/" + job;
    var results = null;

    var plot = null
    $.getJSON(api, function(result){
        plot = $.plot("#placeholder", process_metrics_result(result), options);
    });
    function update() {

        $.getJSON(api, function(result){
            plot.setData(process_metrics_result(result));
            // Since the axes don't change, we don't need to call plot.setupGrid()
            plot.setupGrid();
            plot.draw();
            setTimeout(update, updateInterval);
        });

    }

    update();

}

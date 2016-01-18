var cluster = null;
var job = null;
var period = '1h'; // default period
var plot = null;
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
    var memory_pss = new Array;
    var utc_offset_msec = new Date().getTimezoneOffset() * 60 * 1000;

    $.each(result, function( timestamp_utc, values ) {
        var timestamp = parseInt(timestamp_utc) - utc_offset_msec;
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
function update_job_info(job_info) {
    $('#jobinfo').empty();
    content = "<ul>" +
              "<li>job nodes: " + job_info['nodes'] + "</li>" +
              "<li>metrics producers: " + job_info['producers'] + "</li>" +
              "<li>mute nodes: " + job_info['mutes'] + "</li>" +
              "</ul>";
    $('#jobinfo').append(content);
}

function update() {

    if (update_timeout != null)
        clearTimeout(update_timeout);

    api = "/jobmetrics-restapi/metrics/" + cluster + "/" + job + "/" + period;
    $.getJSON(api, function(result){
        plot.setData(process_metrics_result(result['data']));
        // Since the axes don't change, we don't need to call plot.setupGrid()
        plot.setupGrid();
        plot.draw();
        update_timeout = setTimeout(update, updateInterval);
        update_job_info(result['job']);
    });

}

function set_title() {


    $('#header').empty();
    $('#header').append("<h2>HPC metrics:&nbsp;</h2>");
    $('h2').append("cluster " + cluster,
                   " <a id='jobid' href='#'>job " + job + "</a>");
    $('title').empty();
    $('title').append("HPC metrics: job " + job);
    $('#jobid').click( function() {
        $('#jobinfo').toggle();
        console.log('toggle!');
        return false;
    });
}

function draw_diagram() {

    job = getUrlParameter('job');
    cluster = getUrlParameter('cluster');

    init_period_links();
    set_title(cluster, job);

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
        }
    };

    update();

}

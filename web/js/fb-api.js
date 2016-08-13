https = require('https');

var accessToken = '';
var clientID = global.auth.facebook.client_id,
    clientSecret = global.auth.facebook.client_secret,
    callbackURL = global.auth.facebook.callback_url;

var fbURL = 'https://www.facebook.com/dialog/oauth?client_id=' + clientID;
fbURL += '&redirect_uri=' + callbackURL;
fbURL += '&scope=read_insights,manage_pages';

function parseResponse(response, callback) {
    var output = [];
    response.on('data', function(chunk) {
        output.push(chunk);
    }).on('end', function() {
        callback(JSON.parse(output));
    });
}

exports.fbURL = fbURL;
exports.accessToken = accessToken;

exports.query = function(fields, callback) {
    if (exports.accessToken) {
        var path = '/me?fields=' + fields.join(',');
        path += '&access_token=' + exports.accessToken;

        var options = {
            host : 'graph.facebook.com',
            path : path,
            method : 'GET'
        }

        var req = https.request(options, function(res) {
            if (res.statusCode == 200) {
                // var output = [];
                // res.on('data', function(chunk) {
                //     output.push(chunk);
                // }).on('end', function() {
                //     callback(false, JSON.parse(output));
                // });
                parseResponse(res, function(results) {
                    callback(false, results);
                })
            } else {
                callback(res, {});
            }

        });
        req.end();
        return true;
    } else {
        return false;
    }
}

exports.exchangeToken = function(code) {
    var path = '/v2.3/oauth/access_token?client_id=' + clientID;
    path += '&client_secret=' + clientSecret;
    path += '&redirect_uri=' + callbackURL;
    path += '&code=' + code;

    var options = {
        host : 'graph.facebook.com',
        path : path,
        method: 'GET'
    };

    var req = https.request(options, function (res) {
        if (res.statusCode == 200) {
            parseResponse(res, function(results) {
                exports.accessToken = results.access_token;
                console.log('Set Facebook access token: ' + exports.accessToken);
            });
        }
    });
    req.end();
}

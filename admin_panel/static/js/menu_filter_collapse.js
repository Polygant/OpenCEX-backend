(function($){

var element_2_collapse = '#changelist-filter';
var element_head       = 'h2'
var filter_title       = 'h3'

// this is needed for full table resize after filter menu collapse
var change_list         = '#changelist'


ListFilterCollapsePrototype = {
    bindToggle: function(){
        let that = this;
        this.$filterTitle.click(function(){

            // check if some ul is collapsed
            // open it before slidetoggle all together
            // $(that).children('ul, div.admindatefilter').each(() => {
            //     if($(this).is(":hidden"))
            //         {
            //             $(this).slideToggle();
            //         }
            // })

            console.log(that.$list, that.$list.is('.filtered'))
            if (that.$list.is('.filtered')) {
                that.$filterContentElements.slideDown();
                that.$filterContentTitle.slideDown();
            } else {
                that.$filterContentElements.slideUp();
                that.$filterContentTitle.slideUp();
            }

            that.$list.toggleClass('filtered');

        });

    },
    init: function(filterEl) {
        this.$filterTitle = $(filterEl).children(element_head);
        this.$filterContentTitle = $(filterEl).children(filter_title);
        this.$filterContentElements = $(filterEl).children('ul, div.admindatefilter');
        $(this.$filterTitle).css('cursor', 'pointer');
        this.$list = $(change_list);

        // header collapse
        this.bindToggle();

        // collapsable childrens
        $(element_2_collapse).children(filter_title).each(function(){
            let $title = $(this);
            let $content = $title.nextAll('ul, div.admindatefilter');
            $title.css({'border-bottom':'1px solid grey', 'padding-bottom': '5px', 'cursor': 'pointer'});

            $title.slideUp();
            $content.slideUp();

            $title.click(function(){
                $content.slideToggle();
            });


        });



    }
}
function ListFilterCollapse(filterEl) {
    this.init(filterEl);
}
ListFilterCollapse.prototype = ListFilterCollapsePrototype;

$(document).ready(function(){
    $(element_2_collapse).each(function(){
        var collapser = new ListFilterCollapse(this);
    });

    // close them by default
    // $(element_2_collapse+' '+element_head).click()

    // if some filter was clicked it will be visible for first run only
    // selezione diverse da Default


    $(element_2_collapse).children(filter_title).each(function(){

        lis = $(this).nextAll('ul').eq(0).children('li')
        lis.each(function(cnt) {
          if (cnt > 0)
           {
            if ($(this).hasClass('selected')) {
                $(this).parent().slideDown();
                $(this).parent().prev().slideDown();

                // if some filters is active every filters title (h3)
                // should be visible
                $(element_2_collapse).children(filter_title).each(function(){
                    $(this).slideDown();
                })

                $(change_list).addClass('filtered');

            }
           }
        })

        let div_list = $(this).nextAll('.admindatefilter').find('.vDateField')
        div_list.each(function(cnt) {
            if ($(this).val()) {
                $(this).closest('div.admindatefilter').slideDown();
                // $(this).parent().prev().slideDown();

                // if some filters is active every filters title (h3)
                // should be visible
                $(element_2_collapse).children(filter_title).each(function(){
                    $(this).slideDown();
                })

                $(change_list).addClass('filtered');

            }
        })

    });

});
})(django.jQuery);
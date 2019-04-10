import csv
import json
import traceback
from bika.lims import api
from bika.lims import bikaMessageFactory as _
from bika.lims.exportimport.instruments import IInstrumentAutoImportInterface
from bika.lims.exportimport.instruments import IInstrumentExportInterface
from bika.lims.exportimport.instruments import IInstrumentImportInterface
from bika.lims.exportimport.instruments.instrument import format_keyword
from bika.lims.exportimport.instruments.resultsimport import AnalysisResultsImporter
from bika.lims.utils import t
from cStringIO import StringIO
from DateTime import DateTime
from plone.i18n.normalizer.interfaces import IIDNormalizer
from senaite.instruments.instrument import InstrumentXLSResultsFileParser
from zope.component import getUtility
from zope.interface import implements


class chemstationexport(object):
    implements(IInstrumentExportInterface)
    title = "ChemStationExporter"

    def __init__(self, context):
        self.context = context
        self.request = None

    def Export(self, context, request):
        tray = 1
        now = DateTime().strftime('%Y%m%d-%H%M')
        uc = api.get_tool('uid_catalog')
        instrument = context.getInstrument()
        norm = getUtility(IIDNormalizer).normalize
        filename = '{}-{}.csv'.format(
            context.getId(), norm(instrument.getDataInterface()))
        listname = '{}_{}_{}'.format(
            context.getId(), norm(instrument.Title()), now)
        options = {
            'dilute_factor': 1,
            'method': 'F SO2 & T SO2'
        }
        for k, v in instrument.getDataInterfaceOptions():
            options[k] = v

        # for looking up "cup" number (= slot) of ARs
        parent_to_slot = {}
        layout = context.getLayout()
        for x in range(len(layout)):
            a_uid = layout[x]['analysis_uid']
            p_uid = uc(UID=a_uid)[0].getObject().aq_parent.UID()
            layout[x]['parent_uid'] = p_uid
            if p_uid not in parent_to_slot.keys():
                parent_to_slot[p_uid] = int(layout[x]['position'])

        # write rows, one per PARENT
        header = [listname, options['method']]
        rows = []
        rows.append(header)
        tmprows = []
        ARs_exported = []
        for x in range(len(layout)):
            # create batch header row
            c_uid = layout[x]['container_uid']
            p_uid = layout[x]['parent_uid']
            if p_uid in ARs_exported:
                continue
            cup = parent_to_slot[p_uid]
            tmprows.append([tray,
                            cup,
                            p_uid,
                            c_uid,
                            options['dilute_factor'],
                            ""])
            ARs_exported.append(p_uid)
        tmprows.sort(lambda a, b: cmp(a[1], b[1]))
        rows += tmprows

        ramdisk = StringIO()
        writer = csv.writer(ramdisk, delimiter=';')
        assert(writer)
        writer.writerows(rows)
        result = ramdisk.getvalue()
        ramdisk.close()

        # stream file to browser
        setheader = request.RESPONSE.setHeader
        setheader('Content-Length', len(result))
        setheader('Content-Type', 'text/comma-separated-values')
        setheader('Content-Disposition', 'inline; filename=%s' % filename)
        request.RESPONSE.write(result)


class ChemStationParser(InstrumentXLSResultsFileParser):
    """ Parser
    """

    def _parseline(self, line):
        if self._end_header:
            return self.parse_resultsline(line)
        return self.parse_headerline(line)

    def parse_headerline(self, line):
        """ Parses header lines

            Keywords example:
            Keyword1, Keyword2, Keyword3, ..., end
        """
        if self._end_header:
            # Header already processed
            return 0

        splitted = [token.strip() for token in line.split(self._delimiter)]
        if len(filter(lambda x: len(x), splitted)) == 0:
            self._end_header = True

        if splitted[0].startswith('Sample Name:'):
            ar_id = splitted[0].split(':')[1].strip()
            self._rawresults = {ar_id: [{}]}

        return 0

    def parse_resultsline(self, line):
        """ Parses result lines
        """
        splitted = [token.strip() for token in line.split(self._delimiter)]
        if len(filter(lambda x: len(x), splitted)) == 0:
            return 0

        # Header
        if splitted[0] == 'Comp #':
            self._header = splitted
            return 0

        # DefaultResult
        value_column = 'Amount'
        record = {
            'DefaultResult': value_column,
            'Remarks': ''
        }
        result = splitted[4]
        result = self.get_result(value_column, result, 0)
        record[value_column] = result

        # 3 Interim fields
        value_column = 'RT (min)'
        result = splitted[2]
        result = self.get_result(value_column, result, 0)
        record['ReturnTime'] = result

        value_column = 'Area'
        result = splitted[3]
        result = self.get_result(value_column, result, 0)
        record['Area'] = result

        value_column = 'Q-value'
        result = splitted[6]
        result = self.get_result(value_column, result, 0)
        record['QValue'] = result

        # assign record to kw dict
        kw = splitted[1]
        kw = format_keyword(kw)
        ar_id = self._rawresults.keys()[0]
        self._rawresults[ar_id][0][kw] = record

        return 0

    def get_result(self, column_name, result, line):
        result = str(result)
        if result.startswith('--') or result == '' or result == 'ND':
            return 0.0

        if api.is_floatable(result):
            result = api.to_float(result)
            return result > 0.0 and result or 0.0

        self.err("No valid number ${result} in column (${column_name})",
                 mapping={"result": result,
                          "column_name": column_name},
                 numline=self._numline, line=line)
        return


class ChemStationImporter(AnalysisResultsImporter):
    """ Importer
    """

    # def _process_analysis(self, objid, analysis, values):
    #     ret = AnalysisResultsImporter._process_analysis(
    #         self, objid, analysis, values)
    #     if values.get('Value') and str(values['Value'])[0] in "<>":
    #         analysis.setDetectionLimitOperand('<')
    #     return ret


def __init__(self, parser, context,  override,
             allowed_ar_states=None, allowed_analysis_states=None,
             instrument_uid=None):

        AnalysisResultsImporter.__init__(
            self,
            parser,
            context,
            override=override,
            allowed_ar_states=allowed_ar_states,
            allowed_analysis_states=allowed_analysis_states,
            instrument_uid=instrument_uid)


class chemstationimport(object):
    implements(IInstrumentImportInterface, IInstrumentAutoImportInterface)
    title = "Agilent Masshunter ChemStation"

    def __init__(self, context):
        self.context = context
        self.request = None

    def Import(self, context, request):
        """ Import Form
        """
        infile = request.form['instrument_results_file']
        fileformat = request.form['instrument_results_file_format']
        artoapply = request.form['artoapply']
        override = request.form['results_override']
        instrument = request.form.get('instrument', None)
        errors = []
        logs = []
        warns = []

        # Load the most suitable parser according to file extension/options/etc...
        parser = None
        if not hasattr(infile, 'filename'):
            errors.append(_("No file selected"))
        if fileformat in ('xls', 'xlsx'):
            parser = ChemStationParser(infile, mimetype=fileformat)
        else:
            errors.append(t(_("Unrecognized file format ${fileformat}",
                              mapping={"fileformat": fileformat})))

        if parser:
            # Load the importer
            status = ['sample_received', 'attachment_due', 'to_be_verified']
            if artoapply == 'received':
                status = ['sample_received']
            elif artoapply == 'received_tobeverified':
                status = ['sample_received', 'attachment_due', 'to_be_verified']

            over = [False, False]
            if override == 'nooverride':
                over = [False, False]
            elif override == 'override':
                over = [True, False]
            elif override == 'overrideempty':
                over = [True, True]

            importer = ChemStationImporter(
                parser=parser,
                context=context,
                allowed_ar_states=status,
                allowed_analysis_states=None,
                override=over,
                instrument_uid=instrument)
            tbex = ''
            try:
                importer.process()
                errors = importer.errors
                logs = importer.logs
                warns = importer.warns
            except Exception as e:
                tbex = traceback.format_exc()
                errors.append(tbex)

        results = {'errors': errors, 'log': logs, 'warns': warns}

        return json.dumps(results)